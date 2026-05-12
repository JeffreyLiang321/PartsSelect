"""
One-off script to rebuild urls_to_scrape.txt by re-visiting all listing
pages already in visited_pages.txt and collecting product URLs from them.

Run from repo root:
    python scraper/rebuild_urls.py

This takes ~1-2 hours (1381 pages × 1.5s delay) but does NOT re-scrape
any product detail pages. It only re-visits the listing/category pages
to collect the product URLs, then saves them to data/urls_to_scrape.txt
so the main scraper can proceed directly to Phase 2.
"""

import os
import time
import random
from playwright.sync_api import sync_playwright, Page
from parsers import parse_listing_page

BASE_DIR      = os.path.join(os.path.dirname(__file__), "..", "data")
VISITED_PATH  = os.path.join(BASE_DIR, "visited_pages.txt")
URLS_PATH     = os.path.join(BASE_DIR, "urls_to_scrape.txt")

DELAY_MIN     = 1.2
DELAY_MAX     = 2.5
NAV_TIMEOUT   = 45_000

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [{ name: 'PDF Viewer' }] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = window.chrome || { runtime: {} };
"""

# ── Skip pages that aren't listing pages (category pages are listing pages,
#    the two main appliance pages are not)
SKIP_URLS = {
    "https://www.partselect.com/Refrigerator-Parts.htm",
    "https://www.partselect.com/Dishwasher-Parts.htm",
}

# Infer appliance_type from URL
def get_appliance_type(url: str) -> str:
    if "Dishwasher" in url:
        return "dishwasher"
    return "refrigerator"


def is_blocked(html: str) -> bool:
    return any(x in html[:2000] for x in [
        "Access Denied",
        "You don't have permission to access",
        "errors.edgesuite.net",
    ])


def fetch(page: Page, url: str) -> str | None:
    for attempt in range(1, 4):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            page.wait_for_timeout(1800)
            html = page.content()
            if is_blocked(html):
                print(f"  [block] attempt {attempt}/3")
                if attempt < 3:
                    time.sleep(2 ** attempt + random.uniform(2, 4))
                    continue
                return None
            return html
        except Exception as e:
            print(f"  [error] attempt {attempt}/3: {e}")
            if attempt < 3:
                time.sleep(random.uniform(3, 6))
    return None


def main():
    if not os.path.exists(VISITED_PATH):
        print(f"ERROR: {VISITED_PATH} not found")
        return

    with open(VISITED_PATH, "r") as f:
        all_visited = [l.strip() for l in f if l.strip()]

    # Filter to only listing pages, skip the two main category pages
    listing_pages = [u for u in all_visited if u not in SKIP_URLS]
    print(f"Loaded {len(all_visited)} visited pages")
    print(f"Listing pages to re-visit: {len(listing_pages)}")

    # If urls_to_scrape.txt already exists, load already-processed pages
    # so we can resume if this script is interrupted
    done_pages: set[str] = set()
    existing_urls: list[tuple[str, str, str]] = []
    if os.path.exists(URLS_PATH):
        with open(URLS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) == 3:
                    existing_urls.append((parts[0], parts[1], parts[2]))
        # We don't know which listing pages were already processed,
        # so we track by checking the product URLs we've already seen
        print(f"Found existing {len(existing_urls)} product URLs — will append new ones")

    seen_product_urls: set[str] = {u for u, _, _ in existing_urls}
    all_product_urls = list(existing_urls)

    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="America/New_York",
    )
    context.add_init_script(STEALTH_SCRIPT)
    page = context.new_page()

    try:
        for i, listing_url in enumerate(listing_pages, 1):
            appliance_type = get_appliance_type(listing_url)
            print(f"[{i}/{len(listing_pages)}] {listing_url}")

            html = fetch(page, listing_url)
            if not html:
                print(f"  ✗ failed, skipping")
                time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
                continue

            products = parse_listing_page(html)
            new_count = 0
            for name, url in products:
                if url not in seen_product_urls:
                    seen_product_urls.add(url)
                    all_product_urls.append((url, appliance_type, name))
                    new_count += 1

            print(f"  → {len(products)} products, {new_count} new | total: {len(all_product_urls)}")

            # Save after every page so progress is never lost
            with open(URLS_PATH, "w", encoding="utf-8") as f:
                for url, atype, lname in all_product_urls:
                    f.write(url + "\t" + atype + "\t" + lname + "\n")

            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    finally:
        page.close()
        context.close()
        browser.close()
        pw.stop()

    print(f"\nDone. {len(all_product_urls)} unique product URLs saved to {URLS_PATH}")
    print("Now run: python scraper/scrape.py")


if __name__ == "__main__":
    main()