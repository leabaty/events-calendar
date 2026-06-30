"""
Parser for **cimalpes.fr** newsletters (Cinémathèque de montagne).

Each newsletter puts events in a single ``.diamailedito-text`` paragraph::

    Mercredi 1er juillet - 18H00 à 20H00
    HAPPY HOUR
    Le demi de bière à 2 € …
    …

Usage::

    from parsers.cimalpes import parse
    events = parse(soup, source_url)
"""

import re
import logging
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from . import FRENCH_MONTHS, FRENCH_DAYS, format_title

logger = logging.getLogger(__name__)

# 🎥⛰️  emoji to prepend to every event title
EMOJI = "🎥⛰️ "

# Regex for event header lines, e.g.:
#   "Mercredi 1er juillet - 18H00"
#   "Mercredi 1er juillet - 18H00 à 20H00"
# Handles ordinal suffixes like "1er", "1re", "1ère"
_EVENT_DATE_RE = re.compile(
    r"^(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+"
    r"(\d{1,2})(?:er|re|ère)?\s+"
    r"(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|"
    r"septembre|octobre|novembre|décembre)\s*"
    r"[–\-]?\s*(\d{1,2})H(\d{2})"
    r"(?:\s*à\s*(\d{1,2})H(\d{2}))?",
    re.IGNORECASE,
)

# Day names for detecting event-starting lines
_DAY_NAMES_PATTERN = re.compile(
    r"^(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+",
    re.IGNORECASE,
)


def parse(soup: BeautifulSoup, source_url: str) -> list[dict]:
    """
    Extract events from a Cimalpes newsletter HTML.

    Only lines starting with a French day name followed by a date are treated
    as event starters. Everything else is either event content (title,
    description) or skipped — no stop markers needed.

    Parameters
    ----------
    soup : BeautifulSoup
        Parsed HTML of the email.
    source_url : str
        Identifier for the source (e.g. ``email://…``).

    Returns
    -------
    list[dict]
        Events with keys ``title``, ``date_start``, ``date_end``,
        ``location``, ``description``, ``source_url``.
    """
    events: list[dict] = []

    # Find the main text container
    text_container = soup.select_one(".diamailedito-text")
    if not text_container:
        text_container = soup

    text = text_container.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    current_year = datetime.now().year
    current_event = None

    for line in lines:
        line_lower = line.lower()

        # Skip newsletter header
        if "cette semaine" in line_lower and "cinémathèque" in line_lower:
            continue

        # Does this line look like an event starter (starts with a day name)?
        is_event_start = bool(_DAY_NAMES_PATTERN.match(line))

        if is_event_start:
            match = _EVENT_DATE_RE.match(line)
            if match:
                # Persist previous event
                if current_event and current_event.get("title"):
                    events.append(current_event)

                day = int(match.group(2))
                month_str = match.group(3).lower()
                hour = int(match.group(4))
                minute = int(match.group(5))

                month = FRENCH_MONTHS.get(month_str)
                if not month:
                    continue

                start = datetime(current_year, month, day, hour, minute)

                # Optional end time (e.g. "18H00 à 20H00")
                hour_end = match.group(6)
                minute_end = match.group(7)
                if hour_end and minute_end:
                    end = datetime(current_year, month, day,
                                   int(hour_end), int(minute_end))
                else:
                    end = start + timedelta(hours=2)

                current_event = {
                    "title": "",
                    "date_start": start.isoformat(),
                    "date_end": end.isoformat(),
                    "location": (
                        "La Cinémathèque d'images de montagne, "
                        "7 bis Rue du Forest d'Entrais, 05000 Gap"
                    ),
                    "description": "",
                    "source_url": source_url,
                    "color_id": 11,  # bleu foncé
                }
            elif current_event is not None:
                # Line starts with a day name but doesn't match the full
                # date pattern — treat as description of current event
                prefix = "\n" if current_event["description"] else ""
                current_event["description"] += prefix + line
        elif current_event is not None:
            # Non-day-starting line while we have an active event
            if not current_event["title"]:
                current_event["title"] = format_title(line)
            else:
                prefix = "\n" if current_event["description"] else ""
                current_event["description"] += prefix + line
        # else: non-day-starting line with no active event → skip (handles
        # exposition, VR, opening hours, unsubscribe, etc.)

    # Last event
    if current_event and current_event.get("title"):
        events.append(current_event)

    # Add emoji
    for ev in events:
        if ev["title"]:
            ev["title"] = EMOJI + ev["title"]

    return events
