"""
Parser for **Serre-Ponçon Tourisme** newsletters (contact@serreponcon.com).

Usage::

    from parsers.serreponcon import parse
    events = parse(soup, source_url)
"""

import logging
from datetime import datetime

from bs4 import BeautifulSoup

from . import extract_dates

logger = logging.getLogger(__name__)


def parse(soup: BeautifulSoup, source_url: str) -> list[dict]:
    """
    Extract events from a Serre-Ponçon newsletter HTML.

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

    # TODO: implement Serre-Ponçon parsing once we know the newsletter format
    text = soup.get_text(separator="\n", strip=True)
    dates = extract_dates(text)

    if dates:
        titles = [
            el.get_text(strip=True)
            for el in soup.select("h2, h3, h4, strong, b, .title")
            if el.get_text(strip=True)
        ]
        for i, title in enumerate(titles):
            start, end = dates[i] if i < len(dates) else (None, None)
            events.append({
                "title": title,
                "date_start": start.isoformat() if start else None,
                "date_end": end.isoformat() if end else None,
                "location": "Serre-Ponçon",
                "description": "",
                "source_url": source_url,
                "color_id": 10,  # vert
            })

    return events
