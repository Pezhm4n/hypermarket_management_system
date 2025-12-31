from __future__ import annotations

import logging
import time
from typing import Callable, Dict, Optional

try:
    from selenium import webdriver
    from selenium.common.exceptions import (
        NoSuchElementException,
        TimeoutException,
        WebDriverException,
    )
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager
except Exception:  # pragma: no cover - optional at runtime
    webdriver = None  # type: ignore[assignment]
    Service = object  # type: ignore[assignment]
    By = object  # type: ignore[assignment]
    WebDriverWait = object  # type: ignore[assignment]
    EC = object  # type: ignore[assignment]
    NoSuchElementException = Exception  # type: ignore[assignment]
    TimeoutException = Exception  # type: ignore[assignment]
    WebDriverException = Exception  # type: ignore[assignment]
    ChromeDriverManager = object  # type: ignore[assignment]

logger = logging.getLogger(__name__)

ProductInfo = Dict[str, str]


class IranCodeScraper:
    """
    Human-in-the-loop scraper for https://irancode.ir/.

    It opens a real Chrome browser, navigates to the IranCode search page,
    fills the GTIN / barcode field, and then waits for the human user to
    solve any CAPTCHA and trigger the search.

    Once the page navigates to a product detail URL (containing `/Home/`),
    the scraper parses key fields and returns a minimal product info dict.
    """

    def __init__(self, timeout: float = 120.0) -> None:
        self.timeout = timeout

    def _report(self, cb: Optional[Callable[[str], None]], msg: str) -> None:
        if cb is None or not msg:
            return
        try:
            cb(msg)
        except Exception:
            # UI callbacks must never break the scraping flow.
            pass

    def fetch(
        self,
        barcode: str,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> Optional[ProductInfo]:
        """
        Perform a human-in-the-loop lookup for *barcode* on IranCode.

        The function blocks until either:
          * The user completes the search and the browser navigates to
            a detail page, or
          * The timeout elapses, or
          * The browser window is closed.

        This method is intended to be run from a worker thread.
        """
        barcode = (barcode or "").strip()
        if not barcode:
            return None

        if webdriver is None:
            logger.warning(
                "IranCodeScraper: selenium / webdriver_manager not available; "
                "lookup is disabled."
            )
            self._report(
                status_callback,
                "IranCode lookup is not available on this system (missing Selenium).",
            )
            return None

        driver = None
        try:
            self._report(status_callback, "Opening IranCode website in Chrome...")
            options = webdriver.ChromeOptions()
            # We explicitly want a visible browser window so the user can solve CAPTCHAs.
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")

            try:
                service = Service(ChromeDriverManager().install())
            except Exception as exc:
                logger.exception(
                    "IranCodeScraper: failed to obtain ChromeDriver: %s",
                    exc,
                )
                self._report(
                    status_callback,
                    "Unable to download ChromeDriver for IranCode lookup. "
                    "This service may be blocked in your location.",
                )
                return None

            driver = webdriver.Chrome(service=service, options=options)

            driver.get("https://irancode.ir/")

            # Wait for the search input to be present.
            try:
                search_input = WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "input#gtinSearchInput")
                    )
                )
            except TimeoutException:
                self._report(
                    status_callback,
                    "Could not find IranCode search box. Please check the website.",
                )
                return None

            # Fill the barcode into the input field.
            try:
                search_input.clear()
            except Exception:
                pass
            search_input.send_keys(barcode)

            self._report(
                status_callback,
                "Barcode filled. Please solve the CAPTCHA in the browser "
                "and start the search.",
            )

            start_time = time.time()
            # Remember window handles to detect new tabs/windows opened by the site.
            try:
                initial_handles = set(driver.window_handles)
            except WebDriverException:
                self._report(
                    status_callback,
                    "Browser window was closed before starting IranCode lookup.",
                )
                return None

            # Wait for navigation to a detail page.
            while True:
                if time.time() - start_time > self.timeout:
                    self._report(
                        status_callback,
                        "Timed out waiting for IranCode search result page.",
                    )
                    return None

                # First, try to detect if a new window/tab was opened that contains
                # the product detail page (URL with /Home/ in it).
                try:
                    current_handles = driver.window_handles
                except WebDriverException:
                    self._report(
                        status_callback,
                        "Browser window was closed before completing IranCode lookup.",
                    )
                    return None

                for handle in current_handles:
                    try:
                        driver.switch_to.window(handle)
                        current_url = driver.current_url
                    except WebDriverException:
                        continue

                    if "/Home/" in current_url:
                        # Found a detail page in one of the windows/tabs.
                        break
                else:
                    # No handle with a /Home/ URL found yet; fall back to checking
                    # the current window and keep waiting.
                    try:
                        current_url = driver.current_url
                    except WebDriverException:
                        self._report(
                            status_callback,
                            "Browser window was closed before completing IranCode lookup.",
                        )
                        return None

                    # If user manually navigates away from the site, also stop.
                    if "irancode.ir" not in current_url:
                        self._report(
                            status_callback,
                            "Navigation moved away from IranCode website.",
                        )
                        return None

                    time.sleep(1.0)
                    continue

                # If we reached here via the 'break' in the for-loop, we have a
                # handle whose URL contains /Home/.
                if "/Home/" in current_url:
                    break

            self._report(status_callback, "Result page detected. Parsing details...")
            info = self._parse_detail_page(driver, barcode)
            if info is None:
                self._report(
                    status_callback,
                    "No structured product information found on IranCode page.",
                )
            else:
                self._report(status_callback, "IranCode product information retrieved.")
            return info
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Error during IranCode scraping for %s: %s", barcode, exc)
            self._report(
                status_callback,
                "An unexpected error occurred while querying IranCode.",
            )
            return None
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

    def _parse_detail_page(self, driver, barcode: str) -> Optional[ProductInfo]:
        """
        Parse the product detail page structure described in the requirements.

        We look for li elements with class `d-flex mb-2 pb-1`, each containing
        a muted label (h6.text-muted) and a span with the corresponding value.
        """
        try:
            items = driver.find_elements(By.CSS_SELECTOR, "li.d-flex.mb-2.pb-1")
        except Exception:
            return None

        if not items:
            return None

        extracted: Dict[str, str] = {}

        for item in items:
            try:
                label_el = item.find_element(By.CSS_SELECTOR, "h6.text-muted")
                value_el = item.find_element(By.CSS_SELECTOR, "span")
            except NoSuchElementException:
                continue
            except Exception:
                continue

            label = (getattr(label_el, "text", "") or "").strip()
            value = (getattr(value_el, "text", "") or "").strip()
            if not label or not value:
                continue

            if label == "نام برند":
                extracted["Brand"] = value
            elif label == "نام عملیاتی":
                extracted["OperationalName"] = value
            elif label == "شرح برچسب":
                extracted["LabelDescription"] = value
            elif label == "بریک":
                extracted["Category"] = value

        label_desc = (extracted.get("LabelDescription") or "").strip()
        brand = (extracted.get("Brand") or "").strip()
        operational = (extracted.get("OperationalName") or "").strip()
        category = (extracted.get("Category") or "").strip()

        if label_desc:
            name = label_desc
        elif brand or operational:
            name = f"{brand} {operational}".strip()
        else:
            # Without at least one of these, we do not have a usable name.
            return None

        result: ProductInfo = {"name": name}
        if category:
            result["category"] = category

        return result