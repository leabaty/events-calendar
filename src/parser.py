"""
Parser — extracts events from HTML/text email bodies.

Supports domain-specific parsers for known senders:
    - walpine.fr
    - basp05.com
    - cimalpes.fr

Falls back to a generic regex-based parser for unknown senders.
"""

import re
import logging
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# French month → number mapping
# ---------------------------------------------------------------------------
FRENCH_MONTHS = {
    "janvier": 1, "janv": 1,
    "février": 2, "fevrier": 2, "févr": 2, "fevr": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7, "juil": 7,
    "août": 8, "aout": 8,
    "septembre": 9, "sept": 9,
    "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11,
    "décembre": 12, "decembre": 12, "déc": 12, "dec": 12,
}

FRENCH_DAYS = {
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
    "vendredi": 4, "samedi": 5, "dimanche": 6,
}


def _resolve_french_date(day: int | None, month: int, year: int | None,
                         day_name: str | None = None) -> datetime | None:
    """
    Build a datetime from French date components.
    If *year* is None, uses the current year.
    If *day* is None and *day_name* is given, finds the next occurrence
    of that weekday in the given month/year.
    """
    now = datetime.now()
    year = year or now.year
    month = month

    if day is not None:
        try:
            return datetime(year, month, day)
        except ValueError:
            return None

    if day_name and day_name.lower() in FRENCH_DAYS:
        target_wday = FRENCH_DAYS[day_name.lower()]
        # Start from the 1st of the month
        cursor = datetime(year, month, 1)
        # Find the first occurrence of target weekday
        while cursor.weekday() != target_wday:
            cursor += timedelta(days=1)
        # If that date is already past, take next week
        if cursor < now:
            cursor += timedelta(days=7)
        return cursor

    return None


def _extract_dates(text: str) -> list[tuple[datetime | None, datetime | None]]:
    """
    Extract (start, end) date pairs from French text using regex.
    Returns a list of tuples, each containing (start_datetime, end_datetime).
    Either can be None if only one date is found.
    """
    results = []

    # Pattern 1: "samedi 14 juin" or "samedi 14 juin 2026"
    pat1 = re.compile(
        r"(?:(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+)?"
        r"(\d{1,2})\s+"
        r"(janvier|janv|février|fevrier|févr|fevr|mars|avril|mai|juin|"
        r"juillet|juil|août|aout|septembre|sept|octobre|oct|novembre|nov|"
        r"décembre|decembre|déc|dec)\s*"
        r"(\d{4})?",
        re.IGNORECASE,
    )

    # Pattern 2: "le 14/06/2026"
    pat2 = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")

    # Pattern 3: "14 juin 2026 à 20h30"
    pat3 = re.compile(
        r"(\d{1,2})\s+"
        r"(janvier|janv|février|fevrier|févr|fevr|mars|avril|mai|juin|"
        r"juillet|juil|août|aout|septembre|sept|octobre|oct|novembre|nov|"
        r"décembre|decembre|déc|dec)\s+"
        r"(\d{4})\s*"
        r"(?:à\s*)?(\d{1,2})?h(?:(\d{2}))?",
        re.IGNORECASE,
    )

    # Pattern 4: "du 14 juin au 16 juin 2026" (date range)
    pat_range = re.compile(
        r"du\s+(\d{1,2})\s+"
        r"(janvier|janv|février|fevrier|févr|fevr|mars|avril|mai|juin|"
        r"juillet|juil|août|aout|septembre|sept|octobre|oct|novembre|nov|"
        r"décembre|decembre|déc|dec)\s*"
        r"(?:\d{4}\s+)?au\s+(\d{1,2})\s+"
        r"(janvier|janv|février|fevrier|févr|fevr|mars|avril|mai|juin|"
        r"juillet|juil|août|aout|septembre|sept|octobre|oct|novembre|nov|"
        r"décembre|decembre|déc|dec)\s*"
        r"(\d{4})?",
        re.IGNORECASE,
    )

    # Try date ranges first
    for match in pat_range.finditer(text):
        day_start = int(match.group(1))
        month_start_str = match.group(2).lower()
        day_end = int(match.group(3))
        month_end_str = match.group(4).lower()
        year_str = match.group(5)

        year = int(year_str) if year_str else None
        month_start = FRENCH_MONTHS.get(month_start_str)
        month_end = FRENCH_MONTHS.get(month_end_str)

        if month_start and month_end:
            start = _resolve_french_date(day_start, month_start, year)
            end = _resolve_french_date(day_end, month_end, year)
            if end:
                end = end.replace(hour=23, minute=59)
            results.append((start, end))

    # Pattern 3: specific date + time
    for match in pat3.finditer(text):
        day = int(match.group(1))
        month_str = match.group(2).lower()
        year = int(match.group(3))
        hour = match.group(4)
        minute = match.group(5)

        month = FRENCH_MONTHS.get(month_str)
        if not month:
            continue

        h = int(hour) if hour else 0
        m = int(minute) if minute else 0
        try:
            start = datetime(year, month, day, h, m)
            end = start + timedelta(hours=2)  # default 2-hour duration
            results.append((start, end))
        except ValueError:
            continue

    # Pattern 1: day name + day + month + optional year
    for match in pat1.finditer(text):
        day_name = match.group(1)
        day = int(match.group(2))
        month_str = match.group(3).lower()
        year_str = match.group(4)

        month = FRENCH_MONTHS.get(month_str)
        if not month:
            continue

        year = int(year_str) if year_str else None
        start = _resolve_french_date(day, month, year, day_name)
        if start:
            end = start.replace(hour=23, minute=59)
            results.append((start, end))

    # Pattern 2: numeric date
    for match in pat2.finditer(text):
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        try:
            start = datetime(year, month, day)
            end = start.replace(hour=23, minute=59)
            results.append((start, end))
        except ValueError:
            continue

    return results


# ---------------------------------------------------------------------------
# Domain-specific parsers
# ---------------------------------------------------------------------------

def _parse_walpine(soup: BeautifulSoup, source_url: str) -> list[dict]:
    """Parser for walpine.fr newsletters."""
    events = []
    text = soup.get_text(separator="\n", strip=True)

    # Walpine events often appear in card-like divs
    for card in soup.select(".event-card, .event-item, article, li"):
        title_el = card.select_one(
            "h2, h3, h4, .event-title, .card-title, strong"
        )
        title = title_el.get_text(strip=True) if title_el else ""

        location_el = card.select_one(
            ".location, .lieu, .place, .adresse"
        )
        location = location_el.get_text(strip=True) if location_el else ""

        card_text = card.get_text(separator=" ", strip=True)
        dates = _extract_dates(card_text)

        if title and dates:
            start, end = dates[0] if dates else (None, None)
            events.append({
                "title": title,
                "date_start": start.isoformat() if start else None,
                "date_end": end.isoformat() if end else None,
                "location": location,
                "description": card_text[:500],
                "source_url": source_url,
            })

    # Fallback: whole-body parsing
    if not events:
        dates = _extract_dates(text)
        # Try to find titles from headings
        titles = [
            el.get_text(strip=True)
            for el in soup.select("h2, h3, h4")
            if el.get_text(strip=True)
        ]
        for i, title in enumerate(titles):
            start, end = dates[i] if i < len(dates) else (None, None)
            events.append({
                "title": title,
                "date_start": start.isoformat() if start else None,
                "date_end": end.isoformat() if end else None,
                "location": "",
                "description": "",
                "source_url": source_url,
            })

    return events


def _parse_basp05(soup: BeautifulSoup, source_url: str) -> list[dict]:
    """Parser for basp05.com newsletters."""
    events = []
    text = soup.get_text(separator="\n", strip=True)

    # BASP05 often structures events in tables or div blocks
    for block in soup.select(
        ".event, .agenda-item, tr, .block-content > div, p"
    ):
        block_text = block.get_text(separator=" ", strip=True)
        if not block_text or len(block_text) < 15:
            continue

        dates = _extract_dates(block_text)
        if not dates:
            continue

        # First strong / bold text is often the title
        title_el = block.select_one("strong, b, .title, h3, h4")
        title = (
            title_el.get_text(strip=True)
            if title_el
            else block_text.split(".")[0][:100]
        )

        start, end = dates[0]
        events.append({
            "title": title,
            "date_start": start.isoformat() if start else None,
            "date_end": end.isoformat() if end else None,
            "location": "",
            "description": block_text[:500],
            "source_url": source_url,
        })

    return events


def _parse_cimalpes(soup: BeautifulSoup, source_url: str) -> list[dict]:
    """Parser for cimalpes.fr newsletters."""
    events = []
    text = soup.get_text(separator="\n", strip=True)

    # Cimalpes uses a magazine-like layout
    for block in soup.select(
        ".event, .article, .item, .post, .newsletter-block, li"
    ):
        title_el = block.select_one(
            "h2, h3, h4, .title, .event-title, a[href]"
        )
        title = title_el.get_text(strip=True) if title_el else ""

        location_el = block.select_one(
            ".location, .lieu, .place, .ville"
        )
        location = location_el.get_text(strip=True) if location_el else ""

        block_text = block.get_text(separator=" ", strip=True)
        dates = _extract_dates(block_text)

        if title and dates:
            start, end = dates[0]
            events.append({
                "title": title,
                "date_start": start.isoformat() if start else None,
                "date_end": end.isoformat() if end else None,
                "location": location,
                "description": block_text[:500],
                "source_url": source_url,
            })

    return events


def _parse_generic(text: str, source_url: str) -> list[dict]:
    """
    Generic fallback parser — extracts dates and surrounding text as titles.
    """
    events = []

    # Split into paragraphs / lines
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    for line in lines:
        dates = _extract_dates(line)
        if not dates:
            continue

        start, end = dates[0]
        title = line[:100]  # Use first 100 chars as title
        events.append({
            "title": title,
            "date_start": start.isoformat() if start else None,
            "date_end": end.isoformat() if end else None,
            "location": "",
            "description": line[:500],
            "source_url": source_url,
        })

    return events


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_email(body_html: str, body_text: str, sender: str,
                source_url: str = "") -> list[dict]:
    """
    Parse an email body and extract events.

    Parameters
    ----------
    body_html : str — HTML version of the email body.
    body_text : str — plain-text version of the email body.
    sender : str — sender email address (used to pick a domain-specific parser).
    source_url : str — optional identifier for the source.

    Returns
    -------
    list[dict] — each dict has keys:
        title, date_start, date_end, location, description, source_url
    """
    sender_lower = sender.lower()

    # Choose parser based on sender domain
    if "walpine.fr" in sender_lower and body_html:
        soup = BeautifulSoup(body_html, "html.parser")
        events = _parse_walpine(soup, source_url)
        logger.info("Parsed %d event(s) with walpine parser.", len(events))
        return events

    if "basp05.com" in sender_lower and body_html:
        soup = BeautifulSoup(body_html, "html.parser")
        events = _parse_basp05(soup, source_url)
        logger.info("Parsed %d event(s) with basp05 parser.", len(events))
        return events

    if "cimalpes.fr" in sender_lower and body_html:
        soup = BeautifulSoup(body_html, "html.parser")
        events = _parse_cimalpes(soup, source_url)
        logger.info("Parsed %d event(s) with cimalpes parser.", len(events))
        return events

    # Generic fallback
    text = body_html or body_text
    events = _parse_generic(text, source_url)
    logger.info("Parsed %d event(s) with generic parser.", len(events))
    return events
