"""
Parser for **walpine.fr** newsletters.

Usage::

    from parsers.walpine import parse
    events = parse(soup, source_url)
"""

import logging

from bs4 import BeautifulSoup

from . import extract_dates

logger = logging.getLogger(__name__)


def parse(soup: BeautifulSoup, source_url: str) -> list[dict]:
    """
    Extract events from a Walpine newsletter HTML.

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
        dates = extract_dates(card_text)

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
        dates = extract_dates(text)
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
