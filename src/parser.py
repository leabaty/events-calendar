"""
Parser — dispatcher that routes each email to the right domain-specific parser.

Each parser lives in its own file under ``parsers/``:

- ``parsers/cimalpes.py``  — cimalpes.fr  (Cinémathèque de montagne)
- ``parsers/walpine.py``   — walpine.fr
- ``parsers/basp05.py``    — basp05.com

Adding a new sender?  Just create ``parsers/my_sender.py`` with a
``parse(soup, source_url)`` function and register it in the
``SENDER_MAP`` below.
"""

import logging

from bs4 import BeautifulSoup

from parsers import parse_generic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sender → parser module mapping
# ---------------------------------------------------------------------------
# Each entry: ("partial domain string", parser_module)
# The first matching entry wins.
SENDER_MAP: list[tuple[str, object]] = []


def _discover_parsers():
    """Lazy-import and register all known parsers."""
    if SENDER_MAP:
        return  # already populated

    from parsers import cimalpes, walpine, basp05

    SENDER_MAP.extend([
        ("walpine.fr", walpine),
        ("basp05.com", basp05),
        ("cimalpes.fr", cimalpes),
    ])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_email(body_html: str, body_text: str, sender: str,
                source_url: str = "") -> list[dict]:
    """
    Parse an email body and extract events.

    Parameters
    ----------
    body_html : str
        HTML version of the email body.
    body_text : str
        Plain-text version of the email body.
    sender : str
        Sender email address (used to pick a domain-specific parser).
    source_url : str
        Optional identifier for the source.

    Returns
    -------
    list[dict]
        Each dict has keys ``title``, ``date_start``, ``date_end``,
        ``location``, ``description``, ``source_url``.
    """
    _discover_parsers()
    sender_lower = sender.lower()

    # Try each registered parser
    for domain, module in SENDER_MAP:
        if domain in sender_lower and body_html:
            soup = BeautifulSoup(body_html, "html.parser")
            events = module.parse(soup, source_url)
            logger.info(
                "Parsed %d event(s) with %s parser.", len(events), domain
            )
            return events

    # Generic fallback
    text = body_html or body_text
    events = parse_generic(text, source_url)
    logger.info("Parsed %d event(s) with generic parser.", len(events))
    return events
