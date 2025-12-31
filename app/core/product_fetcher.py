from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

try:  # Optional dependencies; handled gracefully if missing
    import requests
except Exception:  # pragma: no cover - import-time failure
    requests = None  # type: ignore[assignment]

try:
    from bs4 import BeautifulSoup  # type: ignore[import]
except Exception:  # pragma: no cover - import-time failure
    BeautifulSoup = None  # type: ignore[assignment]


ProductInfo = Dict[str, str]


@dataclass
class ProductFetcher:
    """
    Lightweight helper that looks up basic product information for a barcode
    by scraping public web pages.

    The current strategy is:

      1) Try Torob.com search results (Iran-focused price aggregator).
      2) Fall back to a generic web search (Google search results page).

    Only very lightweight parsing is performed: we primarily extract a
    plausible product name from the page title or first result heading.

    All network / parsing errors are swallowed and logged so that failures
    never break the UI; callers simply receive ``None``.
    """

    timeout: float = 6.0

    _USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 HMS-ProductFetcher/1.0 Safari/537.36"
    )

    def _get_session(self):
        """
        Lazily construct and return a requests.Session with browser-like headers.

        Returns None if the requests dependency is not available.
        """
        if requests is None:
            return None

        session = getattr(self, "_session", None)
        if session is None:
            session = requests.Session()
            # Base headers mimicking a real browser to reduce anti-bot blocking.
            session.headers.update(
                {
                    "User-Agent": self._USER_AGENT,
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,"
                        "image/avif,image/webp,image/apng,*/*;q=0.8"
                    ),
                    "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Upgrade-Insecure-Requests": "1",
                    "Connection": "keep-alive",
                }
            )
            self._session = session
        return session

    def fetch_info(
        self,
        barcode: str,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> Optional[ProductInfo]:
        """
        Fetch product info for *barcode*.

        Parameters
        ----------
        barcode:
            Raw barcode string.
        status_callback:
            Optional callable that will be invoked with human-readable
            status messages as the lookup progresses. Intended for UI
            progress indicators; may be ``None``.

        Returns
        -------
        dict | None
            A minimal dictionary like::

                {
                    "name": "Product name",
                    "category": "Optional category",
                }

            or ``None`` if nothing useful could be determined.
        """
        barcode = (barcode or "").strip()
        if not barcode:
            return None

        if requests is None or BeautifulSoup is None:
            logger.warning(
                "ProductFetcher dependencies missing (requests / beautifulsoup4); "
                "online lookup is disabled."
            )
            if status_callback is not None:
                status_callback("Online lookup is not available on this system.")
            return None

        def report(msg: str) -> None:
            if status_callback is not None and msg:
                try:
                    status_callback(msg)
                except Exception:
                    # UI callbacks must never break the lookup
                    pass

        # Try Torob first (better coverage for Iranian products)
        try:
            report("Step 1: Searching Torob...")
            info = self._fetch_from_torob(barcode)
            if info is not None:
                report("Found result on Torob.")
                return info
        except Exception as exc:  # pragma: no cover - very defensive
            logger.exception(
                "Error while fetching product info from Torob for %s: %s",
                barcode,
                exc,
            )

        # Fallback: Google search results page
        try:
            report("Step 2: Searching Google...")
            info = self._fetch_from_google(barcode)
            if info is not None:
                report("Found result on Google.")
                return info
        except Exception as exc:  # pragma: no cover - very defensive
            logger.exception(
                "Error while fetching product info from Google for %s: %s",
                barcode,
                exc,
            )

        report("No product information found.")
        return None

    # ------------------------------------------------------------------ #
    # Individual sources
    # ------------------------------------------------------------------ #
    def _fetch_from_torob(self, barcode: str) -> Optional[ProductInfo]:
        """
        Query Torob.com search results for the barcode and derive a name
        from the page title.
        """
        url = f"https://torob.com/search/?q={barcode}"
        logger.info("ProductFetcher: requesting Torob search for %s", barcode)

        session = self._get_session()
        if session is None:
            return None

        headers = {
            # Pretend we arrived here from a normal browser flow.
            "Referer": "https://www.google.com/",
        }

        resp = session.get(  # type: ignore[call-arg]
            url,
            headers=headers,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            logger.info(
                "ProductFetcher: Torob search for %s returned status %s",
                barcode,
                resp.status_code,
            )
            return None

        soup = BeautifulSoup(resp.text, "html.parser")  # type: ignore[call-arg]
        title = self._extract_title_text(soup, barcode)
        if not title:
            return None

        return {"name": title}

    def _fetch_from_google(self, barcode: str) -> Optional[ProductInfo]:
        """
        Use Google's HTML search results page as a lightweight generic search.

        We try to infer the product name from the page title first, then
        from the first visible result heading if necessary.

        As a last resort, if cleaning heuristics reject everything, we fall
        back to the raw heading text so that the user still sees something
        plausible instead of an empty result.
        """
        search_url = "https://www.google.com/search"
        logger.info("ProductFetcher: requesting Google search for %s", barcode)

        session = self._get_session()
        if session is None:
            return None

        headers = {
            "Referer": "https://www.google.com/",
        }

        resp = session.get(  # type: ignore[call-arg]
            search_url,
            params={"q": barcode, "hl": "fa"},
            headers=headers,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            logger.info(
                "ProductFetcher: Google search for %s returned status %s",
                barcode,
                resp.status_code,
            )
            return None

        soup = BeautifulSoup(resp.text, "html.parser")  # type: ignore[call-arg]

        # Prefer page title
        title = self._extract_title_text(soup, barcode)

        raw_heading_text = ""
        # Fallback: first result heading
        if not title:
            try:
                # Generic heading selector plus a common Google result title class.
                first_heading = soup.select_one(
                    "h3, div.BNeawe.vvjwJb.AP7Wnd"
                )
                if first_heading is not None:
                    raw_heading_text = first_heading.get_text(strip=True)
                    title = self._clean_title(raw_heading_text, barcode)
            except Exception:
                title = ""

        # Last-resort fallback: if cleaning rejected everything but we do have
        # a non-empty heading, return it as-is so the UI can at least show
        # something to the user.
        if not title and raw_heading_text:
            return {"name": raw_heading_text}

        if not title:
            return None

        return {"name": title}

    # ------------------------------------------------------------------ #
    # Parsing helpers
    # ------------------------------------------------------------------ #
    def _extract_title_text(self, soup, barcode: str) -> str:
        if soup is None:
            return ""
        try:
            if soup.title and soup.title.string:
                raw_title = str(soup.title.string)
            else:
                raw_title = ""
        except Exception:
            raw_title = ""
        return self._clean_title(raw_title, barcode)

    def _clean_title(self, title: str, barcode: str) -> str:
        """
        Remove obvious noise (barcode, site name, separators) from a title
        string and return a plausible product name.

        This is intentionally conservative: if after cleaning the title still
        looks like a generic "search results" string or mostly digits, we
        return an empty string instead of guessing.
        """
        if not title:
            return ""

        text = title.strip()
        if not text:
            return ""

        # Remove the raw barcode (digits / alphanumerics) if it appears
        if barcode:
            try:
                text = re.sub(re.escape(barcode), "", text, flags=re.IGNORECASE)
            except re.error:
                text = text.replace(barcode, "")

        # Strip common "search for ..." boilerplate at the beginning
        # (both Persian and English variants).
        search_prefix_patterns = [
            r"^\s*نتایج\s+جستجو\s+برای\s+",
            r"^\s*جستجو\s+برای\s+",
            r"^\s*search\s+results\s+for\s+",
            r"^\s*results\s+for\s+",
            r"^\s*search\s+for\s+",
        ]
        for pattern in search_prefix_patterns:
            new_text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
            if new_text != text:
                text = new_text
                break

        if not text:
            return ""

        # Split on common separators and pick the most likely segment
        separators = ["|", "•", "-", "–", "—", "،"]
        parts = [text]
        for sep in separators:
            if sep in text:
                parts = [p.strip() for p in text.split(sep) if p.strip()]
                break

        # Filter out obvious site names / generic words
        bad_tokens = [
            "torob",
            "ترب",
            "duckduckgo",
            "google",
            "digikala",
            "amazon",
            "جستجو",
            "search",
            "قیمت",
            "خرید",
        ]

        def is_good_segment(segment: str) -> bool:
            seg = (segment or "").strip()
            if not seg:
                return False

            # Remove spaces and common separators for length checks
            compact = re.sub(r"[\s\-\|\u2022،]+", "", seg)
            if len(compact) < 3:
                return False

            # Discard segments that are mostly digits (e.g. just the barcode)
            digit_count = sum(1 for ch in compact if ch.isdigit())
            if digit_count and digit_count >= 0.6 * len(compact):
                return False

            lowered = seg.lower()
            if any(token in lowered for token in bad_tokens):
                return False

            return True

        for segment in parts:
            if is_good_segment(segment):
                return segment

        # All segments looked noisy; treat as unusable.
        return ""