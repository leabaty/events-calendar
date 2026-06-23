"""
Main entry point — orchestrates:
    1. Fetch unread emails from Gmail (events-gap + events-gap/erreur labels)
    2. Parse each email to extract events
    3. Create events in Google Calendar
    4. Mark success → events-gap/traité, failure → events-gap/erreur

Usage:
    python src/main.py
"""

import os
import sys
import logging
from datetime import datetime

# Add src to path if running from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gmail_reader import fetch_unread_emails, mark_as_processed, mark_as_error
from parser import parse_email
from calendar_writer import create_events

logger = logging.getLogger("main")


def setup_logging():
    """Configure logging to stdout with a clean format."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def process_one_email(email: dict) -> bool:
    """
    Parse a single email and create its events.

    Returns ``True`` on success, ``False`` on failure.
    """
    subject = email.get("subject", "(no subject)")
    sender = email.get("sender", "(unknown)")
    source_url = f"email://{sender}/{subject}"

    # ---- Parse ----
    logger.info("Parsing email: '%s' from %s", subject, sender)
    try:
        events = parse_email(
            body_html=email.get("body_html", ""),
            body_text=email.get("body_text", ""),
            sender=sender,
            source_url=source_url,
        )
    except Exception as exc:
        logger.error("Failed to parse email '%s': %s", subject, exc)
        return False

    if not events:
        logger.info("  → No events found — nothing to create.")
        return True  # Not an error, just nothing to do

    logger.info("  → Extracted %d event(s).", len(events))

    # ---- Create events ----
    try:
        created = create_events(events)
        if created < len(events):
            logger.warning(
                "  → Only %d / %d events were created (some may be duplicates).",
                created,
                len(events),
            )
        else:
            logger.info("  → All %d event(s) created successfully.", created)
    except Exception as exc:
        logger.error("Failed to create events for '%s': %s", subject, exc)
        return False

    return True


def main():
    """Main orchestration routine."""
    setup_logging()
    logger.info("=" * 50)
    logger.info("Events Gap — Starting processing cycle")
    logger.info("=" * 50)

    # ------------------------------------------------------------------
    # Step 1: Fetch emails
    # ------------------------------------------------------------------
    logger.info("Step 1/3: Fetching unread emails from Gmail...")
    try:
        emails = fetch_unread_emails()
    except Exception as exc:
        logger.error("Step 1 failed — could not fetch emails: %s", exc)
        sys.exit(1)

    if not emails:
        logger.info("No emails to process. Exiting.")
        logger.info("Summary: 0 mails traités, 0 événements créés.")
        sys.exit(0)

    logger.info("Found %d email(s) to process.", len(emails))

    # ------------------------------------------------------------------
    # Step 2+3: Process each email individually
    # ------------------------------------------------------------------
    ok_ids: list[str] = []
    error_ids: list[str] = []
    total_events = 0

    for email in emails:
        subject = email.get("subject", "(no subject)")
        msg_id = email["id"]

        success = process_one_email(email)

        if success:
            ok_ids.append(msg_id)
        else:
            error_ids.append(msg_id)
            logger.warning("  → Email '%s' will be retried next cycle.", subject)

    # ------------------------------------------------------------------
    # Step 4: Apply labels
    # ------------------------------------------------------------------
    marked_ok = mark_as_processed(ok_ids) if ok_ids else 0
    marked_err = mark_as_error(error_ids) if error_ids else 0

    logger.info("=" * 50)
    logger.info(
        "RÉSUMÉ : %d mail(s) traités, %d en erreur, événements créés.",
        marked_ok,
        marked_err,
    )
    logger.info("=" * 50)
    sys.exit(0 if not error_ids else 1)


if __name__ == "__main__":
    main()
