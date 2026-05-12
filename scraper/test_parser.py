"""
Quick parser test — run from inside the scraper/ directory:
    cd scraper
    python test_parser.py
"""

import sys
import json
import time
from playwright.sync_api import sync_playwright

# Since we run from inside scraper/, parsers is importable directly
from parsers import parse_product_page

TEST_URL = "https://www.partselect.com/PS11752778-Whirlpool-WPW10321304-Refrigerator-Door-Shelf-Bin.htm"
LISTING_NAME = "Whirlpool Refrigerator Door Shelf Bin"
APPLIANCE_TYPE = "refrigerator"

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [{ name: 'PDF Viewer' }] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = window.chrome || { runtime: {} };
"""

with sync_playwright() as pw:
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
    )
    context.add_init_script(STEALTH_SCRIPT)
    page = context.new_page()

    print(f"Fetching {TEST_URL} ...")
    page.goto(TEST_URL, wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_timeout(2500)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1500)
    html = page.content()
    browser.close()

print(f"Got {len(html):,} chars of HTML\n")

part = parse_product_page(html, TEST_URL, APPLIANCE_TYPE, LISTING_NAME)

if not part:
    print("FAILED — parse_product_page returned None")
    sys.exit(1)

print("=" * 60)
for k, v in part.items():
    status = "✓" if v else "⚠ EMPTY"
    display = str(v)[:100] if v else ""
    print(f"  {status}  {k:<22} {display}")
print("=" * 60)
print("\nFull result:")
print(json.dumps(part, indent=2, default=str))