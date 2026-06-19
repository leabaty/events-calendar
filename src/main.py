"""
Main entry point — orchestrates:
    1. Fetch unread emails from Gmail (events-gap label)
    2. Parse each email to extract events
    3. Create events in Google Calendar

Usage:
    python src/main.py
"""

import os
import sys
import logging
from datetime import datetime

# Add src to path if running from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gmail_reader import fetch_unread_emails, mark_as_processed
from parser import parse_email
from calendar_writer import create_events


def setup_logging():
    """Configure logging to stdout with a clean format."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main():
    """Main orchestration routine."""
    setup_logging()
    logger = logging.getLogger("main")
    logger.info("=" * 50)
    logger.info("Events Gap — Starting processing cycle")
    logger.info("=" * 50)

    # ------------------------------------------------------------------
    # Step 1: Fetch unread emails
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
    # Step 2: Parse each email
    # ------------------------------------------------------------------
    logger.info("Step 2/3: Parsing emails to extract events...")
    all_events: list[dict] = []
    parsed_count = 0

    for email in emails:
        subject = email.get("subject", "(no subject)")
        sender = email.get("sender", "(unknown)")
        logger.info("Parsing email: '%s' from %s", subject, sender)

        try:
            events = parse_email(
                body_html=email.get("body_html", ""),
                body_text=email.get("body_text", ""),
                sender=sender,
                source_url=f"email://{sender}/{subject}",
            )
        except Exception as exc:
            logger.error("Failed to parse email '%s': %s", subject, exc)
            continue

        if events:
            logger.info("  → Extracted %d event(s).", len(events))
            all_events.extend(events)
            parsed_count += 1
        else:
            logger.info("  → No events found.")

    logger.info(
        "Parsed %d / %d emails, extracted %d event(s) total.",
        parsed_count,
        len(emails),
        len(all_events),
    )

    # ------------------------------------------------------------------
    # Step 3: Create events in Google Calendar
    # ------------------------------------------------------------------
    logger.info("Step 3/3: Writing events to Google Calendar...")
    created_count = 0

    if all_events:
        try:
            created_count = create_events(all_events)
        except Exception as exc:
            logger.error("Step 3 failed — could not create events: %s", exc)
            # Continue to show summary even on partial failure
    else:
        logger.info("No events to create.")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    logger.info("=" * 50)
    logger.info(
        "RÉSUMÉ : %d mail(s) traités, %d événement(s) créés.",
        len(emails),
        created_count,
    )
    logger.info("=" * 50)

    # Mark all emails as processed
    message_ids = [e["id"] for e in emails]
    marked = mark_as_processed(message_ids)
    logger.info("Marked %d email(s) as processed.", marked)
    sys.exit(0)


if __name__ == "__main__":
    main()
