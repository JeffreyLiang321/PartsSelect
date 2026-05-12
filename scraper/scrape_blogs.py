"""
Scrape all blog post titles and URLs from PartSelect.

Pagination: starts at /blog/, follows a.bold.next until it disappears.
Extraction: a.blog__hero-article (featured) + a.article-card (regular).
Output: data/blogs.json — [{title, url}]

No content scraping — the agent hands users the URL at query time.

Usage:
  python scraper/scrape_blogs.py
  python scraper/scrape_blogs.py --reset
"""

import os
import json
import time
import random
import argparse
from playwright.sync_api import sync_playwright, Page
from bs4 import BeautifulSoup

BASE_DIR     = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_PATH  = os.path.join(BASE_DIR, "blogs.json")

# Config

START_URL   = "https://www.partselect.com/blog/"
BASE_DOMAIN = "https://www.partselect.com"
DELAY_MIN   = 1.5
DELAY_MAX   = 3.0
NAV_TIMEOUT = 45_000

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'PDF Viewer', filename: 'internal-pdf-viewer' },
        { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer' },
    ],
});
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = window.chrome || { runtime: {} };
"""

# Browser helpers

def make_browser():
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
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        timezone_id="America/New_York",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    context.add_init_script(STEALTH_SCRIPT)
    page = context.new_page()
    return pw, browser, context, page


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
            page.wait_for_timeout(2000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)
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


def polite_delay():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


# Parser

def parse_blog_page(html: str) -> tuple[list[dict], str | None]:
    """
    Parse one blog listing page.

    Blog cards come in two flavours — both are <a> tags:
      a.blog__hero-article   — the featured/hero card at the top
      a.article-card         — all regular cards

    Title lives inside div.article-card__title inside the <a>.
    For the hero card the title may be in a heading or the same div.

    Returns:
      blogs    — list of {title, url} found on this page
      next_url — absolute URL of the next (older) page, or None if last page
    """
    soup = BeautifulSoup(html, "lxml")
    blogs = []

    selectors = ["a.blog__hero-article", "a.article-card"]
    seen_hrefs = set()

    for selector in selectors:
        for a in soup.select(selector):
            href = a.get("href", "").strip()
            if not href or href in seen_hrefs:
                continue
            seen_hrefs.add(href)

            # Make absolute
            if href.startswith("/"):
                href = BASE_DOMAIN + href

            # Only keep actual blog post URLs
            if "/blog/" not in href:
                continue

            # Title: prefer div.article-card__title, fall back to heading, then slug
            title_el = (
                a.select_one("div.article-card__title")
                or a.select_one("h1, h2, h3, h4")
            )
            if title_el:
                title = title_el.get_text(strip=True)
            else:
                # Last resort: humanise the URL slug
                slug = href.rstrip("/").split("/")[-1]
                title = slug.replace("-", " ").title()

            if not title:
                continue

            blogs.append({"title": title, "url": href})

    # Pagination: find the "OLDER" / next link
    # DevTools shows: <a class="bold next" href="/content/blog?start=21">
    next_url = None
    next_a = soup.select_one("a.bold.next")
    if next_a:
        next_href = next_a.get("href", "").strip()
        if next_href:
            next_url = BASE_DOMAIN + next_href if next_href.startswith("/") else next_href

    return blogs, next_url


# Main

def main():
    parser = argparse.ArgumentParser(description="PartSelect blog scraper")
    parser.add_argument("--reset", action="store_true",
                        help="Delete blogs.json and start fresh")
    args = parser.parse_args()

    os.makedirs(BASE_DIR, exist_ok=True)

    if args.reset and os.path.exists(OUTPUT_PATH):
        os.remove(OUTPUT_PATH)
        print(f"[reset] Deleted {OUTPUT_PATH}")

    all_blogs: list[dict] = []
    seen_urls: set[str]   = set()

    pw, browser, context, page = make_browser()

    try:
        current_url = START_URL
        page_num    = 1

        while current_url:
            print(f"\n[page {page_num}] {current_url}")

            html = fetch(page, current_url)
            if not html:
                print("  ✗ failed to fetch, stopping")
                break

            blogs, next_url = parse_blog_page(html)

            # Deduplicate across pages (shouldn't happen but to be safe)
            new_blogs = [b for b in blogs if b["url"] not in seen_urls]
            for b in new_blogs:
                seen_urls.add(b["url"])
            all_blogs.extend(new_blogs)

            print(f"  → {len(new_blogs)} new blogs | {len(all_blogs)} total so far")

            # Save after every page so a crash loses at most one page
            with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(all_blogs, f, indent=2, ensure_ascii=False)

            if not next_url:
                print("\n  [done] No next page found — reached last page")
                break

            current_url = next_url
            page_num   += 1
            polite_delay()

    finally:
        page.close()
        context.close()
        browser.close()
        pw.stop()

    # Final save
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_blogs, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"Done. {len(all_blogs)} blog posts saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()