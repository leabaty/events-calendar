"""
Parsers package — one file per newsletter sender.

Each parser module exposes a single ``parse(soup, source_url) -> list[dict]``
function that returns events with the keys:

    title, date_start, date_end, location, description, source_url

Shared French date utilities live here in ``__init__.py``.
"""

import re
import logging
from datetime import datetime, timedelta

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


def format_title(title: str) -> str:
    """
    Format a French event title in proper case (``Abc``).

    - Lowercases everything, then capitalises the first letter
    - Preserves existing capital letters that follow an apostrophe
      (e.g. ``l'Apex``, ``d'Olive``).

    Examples::

        "HAPPY HOUR"                 → "Happy hour"
        "JAM D'OLIVE"                → "Jam d'Olive"
        "ANNIVERSAIRE DE L'APEX"     → "Anniversaire de l'Apex"
        "TIBET, HOMMAGE AU PEUPLE…"  → "Tibet, hommage au peuple…"
        "K2"                         → "K2"
    """
    if not title:
        return title

    # Lowercase everything first
    lower = title.lower()

    # Restore capital letter after an apostrophe (l'X → l'X)
    lower = re.sub(
        r"([dlDLnNsS])'(\w)",
        lambda m: m.group(1) + "'" + m.group(2).upper(),
        lower,
    )

    # Capitalise the very first character
    result = lower[0].upper() + lower[1:]
    return result


def resolve_french_date(day: int | None, month: int, year: int | None,
                        day_name: str | None = None) -> datetime | None:
    """
    Build a datetime from French date components.

    If *year* is ``None``, uses the current year.
    If *day* is ``None`` and *day_name* is given, finds the next occurrence
    of that weekday in the given month/year.
    """
    now = datetime.now()
    year = year or now.year

    if day is not None:
        try:
            return datetime(year, month, day)
        except ValueError:
            return None

    if day_name and day_name.lower() in FRENCH_DAYS:
        target_wday = FRENCH_DAYS[day_name.lower()]
        cursor = datetime(year, month, 1)
        while cursor.weekday() != target_wday:
            cursor += timedelta(days=1)
        if cursor < now:
            cursor += timedelta(days=7)
        return cursor

    return None


def extract_dates(text: str) -> list[tuple[datetime | None, datetime | None]]:
    """
    Extract (start, end) date pairs from French text using regex.

    Returns a list of ``(start_datetime, end_datetime)`` tuples.
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

    # Pattern 4: "du 14 juin au 16 juin 2026"
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
            start = resolve_french_date(day_start, month_start, year)
            end = resolve_french_date(day_end, month_end, year)
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
            end = start + timedelta(hours=2)
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
        start = resolve_french_date(day, month, year, day_name)
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
# Generic fallback
# ---------------------------------------------------------------------------

def parse_generic(text: str, source_url: str) -> list[dict]:
    """
    Generic fallback parser — extracts dates and surrounding text as titles.
    """
    events = []

    lines = [line.strip() for line in text.split("\n") if line.strip()]

    for line in lines:
        dates = extract_dates(line)
        if not dates:
            continue

        start, end = dates[0]
        title = line[:100]
        events.append({
            "title": title,
            "date_start": start.isoformat() if start else None,
            "date_end": end.isoformat() if end else None,
            "location": "",
            "description": line[:500],
            "source_url": source_url,
        })

    return events
