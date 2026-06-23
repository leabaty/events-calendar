"""
Parser for **basp05.com** newsletters.

Usage::

    from parsers.basp05 import parse
    events = parse(soup, source_url)
"""

import logging

from bs4 import BeautifulSoup

from . import extract_dates

logger = logging.getLogger(__name__)


def parse(soup: BeautifulSoup, source_url: str) -> list[dict]:
    """
    Extract events from a BASP05 newsletter HTML.

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

    # BASP05 often structures events in tables or div blocks
    for block in soup.select(
        ".event, .agenda-item, tr, .block-content > div, p"
    ):
        block_text = block.get_text(separator=" ", strip=True)
        if not block_text or len(block_text) < 15:
            continue

        dates = extract_dates(block_text)
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
