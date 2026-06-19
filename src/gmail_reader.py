"""
Gmail Reader — connects to Gmail via OAuth2, reads unprocessed emails
from the 'events-gap' label, and marks them as processed.
"""

import os
import json
import base64
import logging
from email import message_from_bytes
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LABEL_INBOX = "events-gap"
LABEL_PROCESSED = "events-gap/traité"
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def _reconstruct_token(env_var: str = "GMAIL_TOKEN") -> str | None:
    """Write the Gmail token JSON from the environment variable to disk."""
    token_json = os.environ.get(env_var)
    if not token_json:
        logger.error("Environment variable %s is not set.", env_var)
        return None
    token_path = "token.json"
    try:
        with open(token_path, "w") as f:
            f.write(token_json)
        logger.info("Token reconstructed at %s", token_path)
        return token_path
    except OSError as exc:
        logger.error("Failed to write token.json: %s", exc)
        return None


def _get_gmail_service():
    """Build and return an authenticated Gmail API service."""
    token_path = _reconstruct_token()
    if not token_path:
        raise RuntimeError("Could not reconstruct Gmail token.")

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Save refreshed token
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _get_or_create_label(service, label_name: str) -> str | None:
    """Get a Gmail label ID by name, creating it if it doesn't exist."""
    try:
        results = service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])
        for label in labels:
            if label["name"] == label_name:
                return label["id"]

        # Label doesn't exist → create it
        label_body = {
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        created = (
            service.users().labels().create(userId="me", body=label_body).execute()
        )
        logger.info("Created label '%s' (id=%s)", label_name, created["id"])
        return created["id"]
    except HttpError as exc:
        logger.error("Error getting/creating label '%s': %s", label_name, exc)
        return None


def _decode_body(payload) -> str:
    """Recursively extract text (plain or HTML) from a MIME payload."""
    data = None

    if "parts" in payload:
        # Multipart — look for text/html first, then text/plain
        for part in payload["parts"]:
            mime = part.get("mimeType", "")
            if mime == "text/html":
                data = part.get("body", {}).get("data", "")
                break
            elif mime == "text/plain":
                data = part.get("body", {}).get("data", "")
        # If still nothing, recurse into sub-parts
        if not data:
            for part in payload["parts"]:
                data = _decode_body(part)
                if data:
                    break
    else:
        data = payload.get("body", {}).get("data", "")

    if data:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    return ""


def _get_header(headers, name: str) -> str:
    """Extract a header value by name (case-insensitive)."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def fetch_unread_emails() -> list[dict]:
    """
    Fetch all unprocessed emails from the 'events-gap' label.

    Returns a list of dicts:
        {subject, sender, body_html, body_text, date}
    """
    service = _get_gmail_service()
    label_id = _get_or_create_label(service, LABEL_INBOX)

    if not label_id:
        logger.warning("Label '%s' not found, nothing to process.", LABEL_INBOX)
        return []

    try:
        # List messages with the label
        query = f"label:{LABEL_INBOX}"
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, labelIds=[label_id])
            .execute()
        )
        messages = results.get("messages", [])
    except HttpError as exc:
        logger.error("Failed to list messages: %s", exc)
        return []

    if not messages:
        logger.info("No unprocessed emails found under label '%s'.", LABEL_INBOX)
        return []

    emails = []
    for msg_meta in messages:
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_meta["id"], format="full")
                .execute()
            )
        except HttpError as exc:
            logger.error("Failed to fetch message %s: %s", msg_meta["id"], exc)
            continue

        payload = msg.get("payload", {})
        headers = payload.get("headers", [])

        subject = _get_header(headers, "Subject")
        sender = _get_header(headers, "From")
        date = _get_header(headers, "Date")

        body_html = ""
        body_text = ""
        raw_body = _decode_body(payload)

        if payload.get("mimeType") == "text/html":
            body_html = raw_body
        else:
            body_text = raw_body

        # If we have HTML parts inside, prefer those
        if "parts" in payload:
            for part in payload["parts"]:
                mime = part.get("mimeType", "")
                data = part.get("body", {}).get("data", "")
                if data:
                    decoded = base64.urlsafe_b64decode(data).decode(
                        "utf-8", errors="replace"
                    )
                    if mime == "text/html" and not body_html:
                        body_html = decoded
                    elif mime == "text/plain" and not body_text:
                        body_text = decoded

        email = {
            "id": msg_meta["id"],
            "subject": subject,
            "sender": sender,
            "body_html": body_html,
            "body_text": body_text or body_html,  # fallback if only HTML
            "date": date,
        }
        emails.append(email)
        logger.debug("Fetched email: '%s' from %s", subject, sender)

    return emails


def mark_as_processed(message_ids: list[str]) -> int:
    """
    Apply the 'events-gap/traité' label and remove the 'events-gap' label
    from the given message IDs.

    Returns the number of successfully processed messages.
    """
    if not message_ids:
        return 0

    service = _get_gmail_service()

    processed_label_id = _get_or_create_label(service, LABEL_PROCESSED)
    inbox_label_id = _get_or_create_label(service, LABEL_INBOX)

    if not processed_label_id or not inbox_label_id:
        logger.error("Cannot mark messages as processed — labels missing.")
        return 0

    count = 0
    for msg_id in message_ids:
        try:
            service.users().messages().modify(
                userId="me",
                id=msg_id,
                body={
                    "addLabelIds": [processed_label_id],
                    "removeLabelIds": [inbox_label_id],
                },
            ).execute()
            count += 1
        except HttpError as exc:
            logger.error("Failed to modify message %s: %s", msg_id, exc)

    logger.info("Marked %d / %d messages as processed.", count, len(message_ids))
    return count
