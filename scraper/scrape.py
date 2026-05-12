"""
PartSelect parts scraper.

3-level crawl:
  Level 1: Main appliance page → brand links
  Level 2: Brand page → product URLs + subcategory links
  Level 3: Brand+type subcategory → product URLs
  Product: Visit each URL → extract all fields → write to CSV

Usage:
    python scraper/scrape.py              # full run
    python scraper/scrape.py --dry-run    # Phase 1 only, no product scraping
    python scraper/scrape.py --debug      # print HTML of first page
    python scraper/scrape.py --reset      # delete progress files and start fresh
"""

import re
import os
import csv
import time
import argparse
import random
from playwright.sync_api import sync_playwright, Page

from parsers import (
    parse_brand_links,
    parse_listing_page,
    parse_related_links,
    parse_product_page,
)

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR        = os.path.join(os.path.dirname(__file__), "..", "data")
CSV_PATH        = os.path.join(BASE_DIR, "parts.csv")
VISITED_PATH    = os.path.join(BASE_DIR, "visited_pages.txt")
URLS_PATH       = os.path.join(BASE_DIR, "urls_to_scrape.txt")

# ── Entry points ──────────────────────────────────────────────────────────────

APPLIANCE_PAGES = [
    ("https://www.partselect.com/Refrigerator-Parts.htm", "refrigerator"),
    ("https://www.partselect.com/Dishwasher-Parts.htm",   "dishwasher"),
]

# ── Config ────────────────────────────────────────────────────────────────────

DELAY_MIN      = 1.5
DELAY_MAX      = 3.0
MAX_RETRIES    = 4
NAV_TIMEOUT_MS = 45_000

CSV_FIELDS = [
    "part_name", "part_id", "mpn_id", "part_price",
    "install_difficulty", "install_time", "symptoms", "appliance_types",
    "replace_parts", "brand", "availability", "in_stock",
    "install_video_url", "product_url", "appliance_type",
    "description", "compatible_models", "image_url",
    "rating", "review_count",
]

# ── Anti-detection init script ────────────────────────────────────────────────

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
const _origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (p) =>
    p.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : _origQuery(p);
"""

# ── Progress helpers ──────────────────────────────────────────────────────────

def load_visited_pages() -> set[str]:
    if not os.path.exists(VISITED_PATH):
        return set()
    with open(VISITED_PATH, "r") as f:
        return {line.strip() for line in f if line.strip()}


def mark_page_visited(url: str):
    os.makedirs(BASE_DIR, exist_ok=True)
    with open(VISITED_PATH, "a") as f:
        f.write(url + "\n")


def load_scraped_ps_numbers() -> set[str]:
    if not os.path.exists(CSV_PATH):
        return set()
    done = set()
    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("part_id"):
                done.add(row["part_id"])
    return done


def append_to_csv(part: dict):
    os.makedirs(BASE_DIR, exist_ok=True)
    file_exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(part)


def count_csv_rows() -> int:
    if not os.path.exists(CSV_PATH):
        return 0
    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def save_product_urls(urls: list[tuple[str, str, str]]):
    """Persist collected product URLs so Phase 1 does not need to re-run on resume."""
    os.makedirs(BASE_DIR, exist_ok=True)
    with open(URLS_PATH, "w", encoding="utf-8") as f:
        for url, appliance_type, listing_name in urls:
            f.write(url + "\t" + appliance_type + "\t" + listing_name + "\n")
    print(f"[urls] Saved {len(urls)} product URLs to {URLS_PATH}")


def load_product_urls() -> list[tuple[str, str, str]]:
    """Load previously collected product URLs from disk."""
    if not os.path.exists(URLS_PATH):
        return []
    urls = []
    with open(URLS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("	")
            if len(parts) == 3:
                urls.append((parts[0], parts[1], parts[2]))
    print(f"[urls] Loaded {len(urls)} product URLs from {URLS_PATH}")
    return urls


def reset_progress():
    for path in [VISITED_PATH, URLS_PATH]:
        if os.path.exists(path):
            os.remove(path)
            print(f"[reset] Deleted {path}")
    print("[reset] parts.csv kept — delete manually if you want a full fresh start")


# ── Browser ───────────────────────────────────────────────────────────────────

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
            "Sec-Ch-Ua-Platform": '"macOS"',
        },
    )
    context.add_init_script(STEALTH_SCRIPT)
    page = context.new_page()
    return pw, browser, context, page


def is_blocked(html: str) -> bool:
    if not html:
        return True
    return any(x in html[:2000] for x in [
        "Access Denied",
        "You don't have permission to access",
        "errors.edgesuite.net",
    ])


def fetch(page: Page, url: str, debug: bool = False) -> str | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            page.wait_for_timeout(2000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)
            html = page.content()

            if is_blocked(html):
                print(f"    [{attempt}/{MAX_RETRIES}] Akamai block — backing off")
                if attempt < MAX_RETRIES:
                    time.sleep((2 ** attempt) + random.uniform(2, 5))
                    continue
                return None

            if debug:
                print(f"\n[debug] {url} — {len(html)} chars")
                print(html[:3000])

            return html
        except Exception as e:
            print(f"    [{attempt}/{MAX_RETRIES}] Error: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(random.uniform(3, 6))
    return None


def polite_delay():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


# ── Phase 1: collect all product URLs ────────────────────────────────────────

def collect_all_product_urls(
    page: Page,
    debug: bool = False,
) -> list[tuple[str, str, str]]:
    """
    Returns list of (product_url, appliance_type, listing_name).
    listing_name is the raw title from the category page (e.g. 'Whirlpool Refrigerator Door Shelf Bin'),
    passed through to drive the part_name field in the expected naming format.
    """
    visited = load_visited_pages()
    product_urls: list[tuple[str, str, str]] = []
    seen_product_urls: set[str] = set()

    for appliance_url, appliance_type in APPLIANCE_PAGES:

        print(f"\n{'='*60}")
        print(f"[phase1] {appliance_type.upper()} — {appliance_url}")
        print(f"{'='*60}")

        # ── Level 1: get brand links ──────────────────────────────────────────
        if appliance_url in visited:
            print(f"  [skip] main page already visited")
        else:
            html = fetch(page, appliance_url, debug=debug)
            debug = False  # only debug first page
            if not html:
                print(f"  ✗ could not fetch main page, skipping {appliance_type}")
                continue
            mark_page_visited(appliance_url)

            brand_links = parse_brand_links(html)
            print(f"  → {len(brand_links)} brand links found")

        # always re-fetch so we have brand_links regardless of resume state
        html = fetch(page, appliance_url)
        if not html:
            continue
        brand_links = parse_brand_links(html)
        polite_delay()

        # ── Level 2: visit each brand page ───────────────────────────────────
        for b_idx, brand_url in enumerate(brand_links, 1):
            print(f"\n  [brand {b_idx}/{len(brand_links)}] {brand_url}")

            if brand_url in visited:
                print(f"    [skip] already visited")
                continue

            html = fetch(page, brand_url)
            if not html:
                mark_page_visited(brand_url)  # mark to skip on retry
                polite_delay()
                continue

            # Products directly on the brand page
            brand_products = parse_listing_page(html)
            new = [(u, appliance_type, name) for name, u in brand_products
                   if u not in seen_product_urls]
            for _, u, _ in new:
                seen_product_urls.add(u)
            product_urls.extend(new)
            print(f"    → {len(brand_products)} products on brand page")

            # Related subcategory links
            subcats = parse_related_links(html)
            print(f"    → {len(subcats)} subcategory links")

            mark_page_visited(brand_url)
            polite_delay()

            # ── Level 3: visit each subcategory ──────────────────────────────
            for s_idx, sub_url in enumerate(subcats, 1):
                if sub_url in visited:
                    continue

                html = fetch(page, sub_url)
                if not html:
                    mark_page_visited(sub_url)
                    polite_delay()
                    continue

                sub_products = parse_listing_page(html)
                new = [(u, appliance_type, name) for name, u in sub_products
                       if u not in seen_product_urls]
                for _, u, _ in new:
                    seen_product_urls.add(u)
                product_urls.extend(new)

                mark_page_visited(sub_url)
                polite_delay()

            print(f"    → running total: {len(product_urls)} product URLs")

    print(f"\n[phase1 complete] {len(product_urls)} unique product URLs collected")
    save_product_urls(product_urls)
    return product_urls


# ── Phase 2: scrape each product page ─────────────────────────────────────────

def scrape_all_products(
    page: Page,
    product_urls: list[tuple[str, str, str]],
    dry_run: bool = False,
):
    already_done = load_scraped_ps_numbers()
    print(f"[phase2] {len(already_done)} parts already in CSV, will skip")

    total = len(product_urls)
    success = skipped = failed = 0

    for i, (url, appliance_type, listing_name) in enumerate(product_urls, 1):
        m = re.match(r".*/PS(\d+)-", url)
        ps_from_url = f"PS{m.group(1)}" if m else None

        if ps_from_url and ps_from_url in already_done:
            skipped += 1
            if skipped % 50 == 0:
                print(f"  [{i}/{total}] ...skipping already-scraped parts ({skipped} skipped so far)")
            continue

        if dry_run:
            print(f"  [{i}/{total}] DRY  {url}")
            continue

        print(f"  [{i}/{total}] GET  {url}")
        html = fetch(page, url)

        if not html:
            print(f"             ✗ blocked or fetch failed")
            failed += 1
            polite_delay()
            continue

        part = parse_product_page(html, url, appliance_type, listing_name)
        if not part or not part.get("part_id"):
            print(f"             ✗ parse failed")
            failed += 1
        else:
            if part["part_id"] in already_done:
                skipped += 1
            else:
                append_to_csv(part)
                already_done.add(part["part_id"])
                price_str = f"${part['part_price']}" if part['part_price'] else "no price"
                print(
                    f"             ✓ {part['part_id']} | "
                    f"{part['part_name'][:45]} | "
                    f"{price_str} | "
                    f"diff={part['install_difficulty'] or '?'}"
                )
                success += 1

        polite_delay()

    print(f"\n[phase2 done] success={success}  skipped={skipped}  failed={failed}")
    print(f"[phase2 done] total rows in CSV: {count_csv_rows()}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PartSelect 3-level scraper")
    parser.add_argument("--dry-run", action="store_true",
                        help="Phase 1 only — collect URLs, don't scrape products")
    parser.add_argument("--debug", action="store_true",
                        help="Print first 3000 chars of HTML on first page")
    parser.add_argument("--reset", action="store_true",
                        help="Delete progress files and start fresh")
    args = parser.parse_args()

    os.makedirs(BASE_DIR, exist_ok=True)

    if args.reset:
        reset_progress()
        return

    visited = load_visited_pages()
    if visited:
        print(f"[resume] Found {len(visited)} already-visited listing pages — resuming")
    else:
        print("[start] Fresh run")

    pw, browser, context, page = make_browser()
    try:
        # ── Phase 1 ───────────────────────────────────────────────────────────
        # If urls_to_scrape.txt already exists, Phase 1 was completed on a
        # previous run — load from file and skip directly to Phase 2.
        cached_urls = load_product_urls()
        if cached_urls:
            print(f"\n[phase1] Skipping — loaded {len(cached_urls)} product URLs from cache")
            product_urls = cached_urls
        else:
            print("\n" + "="*60)
            print("PHASE 1 — collecting product URLs (3-level crawl)")
            print("="*60)
            product_urls = collect_all_product_urls(page, debug=args.debug)

        print("\n" + "="*60)
        print("PHASE 2 — scraping product detail pages → parts.csv")
        print("="*60)
        scrape_all_products(page, product_urls, dry_run=args.dry_run)

    finally:
        page.close()
        context.close()
        browser.close()
        pw.stop()


if __name__ == "__main__":
    main()