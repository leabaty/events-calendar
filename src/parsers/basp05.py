"""
Parser for **basp05.com** newsletters (Apex Brewpub).

The Apex newsletter format lists events as bullet-point lines with the day
and day number only (no month — it comes from the newsletter context, e.g.
the subject "Newsletter Apex Brewpub Juillet 2026")::

    - Samedi 04 : *ANNIVERSAIRE …* Concert …
    - Mardi 07 :  *JAM D'OLIVE *: Scène ouverte …

Usage::

    from parsers.basp05 import parse
    events = parse(soup, source_url)
"""

import re
import logging
from datetime import datetime

from bs4 import BeautifulSoup

from . import FRENCH_MONTHS, format_title

logger = logging.getLogger(__name__)

# 🍻 emoji to prepend to every event title
EMOJI = "🍻 "

# Pattern for event lines in plain text, e.g.:
#   "- Samedi 04 : *TITLE* : description"
#   "- Samedi 04 : TITLE : description"
#   "Samedi 04 : *TITLE* description"
_EVENT_LINE_RE = re.compile(
    r"^\s*[–\-•·*]?\s*"
    r"(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+"
    r"(\d{1,2})(?:er|re|ère)?\s*:\s*"
    r"\*?\s*(.+?)\s*\*?\s*(?::\s*(.*))?$",
    re.IGNORECASE | re.DOTALL,
)

# Pattern to extract month + year from newsletter context, e.g.:
#   "Juillet 2026" or "juillet 2026"
_MONTH_YEAR_RE = re.compile(
    r"(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|"
    r"septembre|octobre|novembre|décembre|decembre)\s+(\d{4})",
    re.IGNORECASE,
)

# For HTML parsing: find event divs by looking for bold text near bullet
# patterns in flat div elements
_HTML_EVENT_RE = re.compile(
    r"^\s*[–\-•·*]?\s*"
    r"(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+"
    r"(\d{1,2})(?:er|re|ère)?",
    re.IGNORECASE,
)


def _extract_month_year(text: str, source_url: str = "") -> tuple[int | None, int | None]:
    """Extract (month, year) from newsletter context.

    Tries in order:
    1. ``"Juillet 2026"`` in the ``source_url`` (which embeds the subject
       line — most reliable)
    2. ``"Juillet 2026"`` in the body text (month + year together)
    3. A standalone month name in body text → use current year
    """
    now = datetime.now()

    # 1. Try source_url first (embeds the subject, e.g. "Juillet 2026")
    if source_url:
        match = _MONTH_YEAR_RE.search(source_url)
        if match:
            month = FRENCH_MONTHS.get(match.group(1).lower())
            year = int(match.group(2))
            return month, year

    # 2. Month + year together in text
    match = _MONTH_YEAR_RE.search(text)
    if match:
        month = FRENCH_MONTHS.get(match.group(1).lower())
        year = int(match.group(2))
        return month, year

    # 3. Standalone month name in text → current year
    #    Pick the LAST month name to avoid false positives from generic text
    month_pat = re.compile(
        r"(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|"
        r"septembre|octobre|novembre|décembre|decembre)",
        re.IGNORECASE,
    )
    matches = list(month_pat.finditer(text))
    if matches:
        month = FRENCH_MONTHS.get(matches[-1].group(1).lower())
        return month, now.year

    return None, None


def parse(soup: BeautifulSoup, source_url: str) -> list[dict]:
    """
    Extract events from a BASP05 / Apex Brewpub newsletter HTML.

    The month and year are inferred from the newsletter context (e.g. subject
    line or body text containing "Juillet 2026"). Each event line matching
    ``- Day DD : Title`` is extracted.

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
    seen: set[tuple[int, str]] = set()  # (day, normalized_title) dedup

    # Extract month/year from the full email text
    all_text = soup.get_text(separator="\n", strip=True)
    month, year = _extract_month_year(all_text, source_url)
    if not month or not year:
        logger.warning(
            "Could not extract month/year from newsletter — no events parsed."
        )
        return []

    # Strategy 1: Parse HTML structure — find <b> tags inside <div> elements
    # that contain event-like text
    for div in soup.find_all("div"):
        div_text = div.get_text(strip=True)
        if not div_text:
            continue

        # Check if this div looks like an event line
        if not _HTML_EVENT_RE.match(div_text):
            continue

        # Extract title from <b> tag if present
        bold = div.find("b")
        if bold:
            title = format_title(bold.get_text(strip=True).rstrip(":"))
        else:
            # Fallback: extract title after the date part
            title_match = _EVENT_LINE_RE.match(div_text)
            title = title_match.group(3).strip() if title_match else div_text

        # Get full description
        description = div_text

        # Parse day number
        day_match = _HTML_EVENT_RE.match(div_text)
        if not day_match:
            continue
        day = int(day_match.group(2))

        # Build dates
        try:
            start = datetime(year, month, day, 19, 0)  # default start 19h
            end = datetime(year, month, day, 23, 0)     # default end 23h
        except ValueError:
            continue

        # Dedup check
        key = (day, title.lower().strip())
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "title": EMOJI + title,
            "date_start": start.isoformat(),
            "date_end": end.isoformat(),
            "location": "Apex Brewpub, 05000 Gap",
            "description": description,
            "source_url": source_url,
            "color_id": 5,  # jaune
        })

    # Strategy 2: Text fallback — parse lines if HTML approach found nothing
    if not events:
        lines = all_text.split("\n")
        for line in lines:
            line = line.strip()
            match = _EVENT_LINE_RE.match(line)
            if not match:
                continue

            day_name = match.group(1)
            day = int(match.group(2))
            title = format_title(match.group(3).strip().rstrip(":"))
            description = (match.group(4) or "").strip()

            try:
                start = datetime(year, month, day, 19, 0)
                end = datetime(year, month, day, 23, 0)
            except ValueError:
                continue

            # Dedup check
            key = (day, title.lower().strip())
            if key in seen:
                continue
            seen.add(key)

            events.append({
                "title": EMOJI + title,
                "date_start": start.isoformat(),
                "date_end": end.isoformat(),
                "location": "Apex Brewpub, 05000 Gap",
                "description": description,
                "source_url": source_url,
                "color_id": 5,  # jaune
            })

    if not events:
        logger.info("No events matched in the Apex newsletter.")

    return events
