"""
Calendar Writer — connects to Google Calendar via a Service Account,
creates events with deduplication.
"""

import os
import json
import logging
from datetime import datetime, timezone

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _reconstruct_credentials(env_var: str = "GOOGLE_CALENDAR_CREDENTIALS") -> str | None:
    """Write the service account JSON from the environment variable to disk."""
    creds_json = os.environ.get(env_var)
    if not creds_json:
        logger.error("Environment variable %s is not set.", env_var)
        return None
    creds_path = "service_account.json"
    try:
        with open(creds_path, "w") as f:
            f.write(creds_json)
        logger.info("Service account credentials reconstructed at %s", creds_path)
        return creds_path
    except OSError as exc:
        logger.error("Failed to write service_account.json: %s", exc)
        return None


def _get_calendar_service():
    """Build and return an authenticated Google Calendar service."""
    creds_path = _reconstruct_credentials()
    if not creds_path:
        raise RuntimeError("Could not reconstruct service account credentials.")

    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return build("calendar", "v3", credentials=creds)


def _event_exists(service, calendar_id: str, title: str,
                  date_start: str) -> bool:
    """
    Check if an event with the same title and start date already exists
    in the calendar (case-insensitive title comparison).
    """
    try:
        # Build RFC3339 timestamps with timezone
        date_prefix = date_start[:10]  # "2026-06-24"
        time_min = f"{date_prefix}T00:00:00+02:00"
        time_max = f"{date_prefix}T23:59:59+02:00"

        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=50,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        existing_events = events_result.get("items", [])
    except HttpError as exc:
        logger.error("Failed to list events for dedup check: %s", exc)
        return False

    for existing in existing_events:
        existing_title = existing.get("summary", "").strip().lower()
        if existing_title == title.strip().lower():
            logger.debug(
                "Duplicate found: '%s' on %s — skipping.", title, date_start
            )
            return True
    return False


def create_events(events: list[dict]) -> int:
    """
    Create Google Calendar events with deduplication.

    Parameters
    ----------
    events : list[dict] — each dict must contain:
        title, date_start, date_end, location, description, source_url

    Returns
    -------
    int — number of events successfully created.
    """
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
    if not calendar_id:
        logger.error("GOOGLE_CALENDAR_ID environment variable is not set.")
        return 0

    service = _get_calendar_service()
    created_count = 0

    for event in events:
        title = event.get("title", "").strip()
        date_start = event.get("date_start")
        date_end = event.get("date_end")
        location = event.get("location", "")
        description = event.get("description", "")
        source_url = event.get("source_url", "")
        color_id = event.get("color_id")

        if not title or not date_start:
            logger.warning("Skipping event with missing title or date_start.")
            continue

        # Build description with source URL
        full_description = description
        if source_url:
            full_description = f"{description}\n\nSource: {source_url}"

        # Deduplication check
        if _event_exists(service, calendar_id, title, date_start):
            logger.info("Skipping duplicate event: '%s'", title)
            continue

        # Build the Google Calendar event body
        event_body = {
            "summary": title,
            "description": full_description,
        }

        if location:
            event_body["location"] = location

        if color_id is not None:
            event_body["colorId"] = str(color_id)

        # Format dates (ISO string → RFC3339)
        try:
            start_dt = datetime.fromisoformat(date_start)
            end_dt = (
                datetime.fromisoformat(date_end)
                if date_end
                else start_dt.replace(hour=23, minute=59)
            )
        except (ValueError, TypeError) as exc:
            logger.warning("Invalid date for '%s': %s", title, exc)
            continue

        # All-day event if times are at midnight
        if start_dt.hour == 0 and start_dt.minute == 0:
            event_body["start"] = {
                "date": start_dt.date().isoformat(),
                "timeZone": "Europe/Paris",
            }
            event_body["end"] = {
                "date": end_dt.date().isoformat(),
                "timeZone": "Europe/Paris",
            }
        else:
            event_body["start"] = {
                "dateTime": start_dt.isoformat(),
                "timeZone": "Europe/Paris",
            }
            event_body["end"] = {
                "dateTime": end_dt.isoformat(),
                "timeZone": "Europe/Paris",
            }

        try:
            created = (
                service.events()
                .insert(calendarId=calendar_id, body=event_body)
                .execute()
            )
            created_count += 1
            logger.info("Created event: '%s' (id=%s)", title, created.get("id"))
        except HttpError as exc:
            logger.error("Failed to create event '%s': %s", title, exc)

    logger.info("Total events created: %d", created_count)
    return created_count
