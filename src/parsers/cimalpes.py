"""
Parser for **cimalpes.fr** newsletters (Cinémathèque de montagne).

Each newsletter puts events in a single ``.diamailedito-text`` paragraph::

    Mercredi 24 juin - 17H00
    OZI, LA VOIX DE LA FORÊT
    Réalisé par Tim Harper – 2025 – 87' …
    …

Usage::

    from parsers.cimalpes import parse
    events = parse(soup, source_url)
"""

import re
import logging
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from . import FRENCH_MONTHS

logger = logging.getLogger(__name__)

# 🎥⛰️  emoji to prepend to every event title
EMOJI = "🎥⛰️ "

# Regex for event header lines, e.g.:
#   "Mercredi 24 juin - 17H00"
#   "Mercredi 24 juin - 18H00 à 20H00"
_EVENT_DATE_RE = re.compile(
    r"^(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+"
    r"(\d{1,2})\s+"
    r"(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|"
    r"septembre|octobre|novembre|décembre)\s*"
    r"[–\-]?\s*(\d{1,2})H(\d{2})"
    r"(?:\s*à\s*(\d{1,2})H(\d{2}))?",
    re.IGNORECASE,
)

# Lines containing any of these stop the event list
_STOP_MARKERS = [
    "exposition",
    "réalité virtuelle",
    "realite virtuelle",
    "une nouvelle expo",
    "ouverture",
    "plus d'infos",
    "se désinscrire",
    "désinscrire",
]


def parse(soup: BeautifulSoup, source_url: str) -> list[dict]:
    """
    Extract events from a Cimalpes newsletter HTML.

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

        # Stop at non-event sections
        if any(marker in line_lower for marker in _STOP_MARKERS):
            break

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

            # Optional end time  (e.g. "18H00 à 20H00")
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
            # First non-date line → title, rest → description
            if not current_event["title"]:
                current_event["title"] = line
            else:
                prefix = "\n" if current_event["description"] else ""
                current_event["description"] += prefix + line

    # Last event
    if current_event and current_event.get("title"):
        events.append(current_event)

    # Add emoji
    for ev in events:
        if ev["title"]:
            ev["title"] = EMOJI + ev["title"]

    return events
