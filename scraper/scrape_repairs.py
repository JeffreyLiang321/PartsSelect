import os
import re
import json
import time
import random
import argparse
import sqlite3
from playwright.sync_api import sync_playwright, Page
from bs4 import BeautifulSoup

BASE_DIR     = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_PATH  = os.path.join(BASE_DIR, "repair_guides.json")
DB_PATH      = os.path.join(BASE_DIR, "parts.db")

REPAIR_PAGES = [
    ("https://www.partselect.com/Repair/Refrigerator/", "refrigerator"),
    ("https://www.partselect.com/Repair/Dishwasher/",   "dishwasher"),
]

# Config 

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
const _origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (p) =>
    p.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : _origQuery(p);
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
                print(f"    [block] attempt {attempt}/3")
                if attempt < 3:
                    time.sleep(2 ** attempt + random.uniform(2, 4))
                    continue
                return None
            return html
        except Exception as e:
            print(f"    [error] attempt {attempt}/3: {e}")
            if attempt < 3:
                time.sleep(random.uniform(3, 6))
    return None


def polite_delay():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


# Level 1 parser

def parse_symptom_list(html: str, appliance: str) -> list[dict]:
    """
    Parse the main repair listing page (/Repair/Refrigerator/ etc.).
    Each symptom card is an <a> inside div.symptom-list.

    Returns list of dicts:
      appliance, symptom, description, pct_reported, url
    """
    soup = BeautifulSoup(html, "lxml")
    results = []

    symptom_list = soup.select_one("div.symptom-list")
    if not symptom_list:
        print("  [warn] div.symptom-list not found on listing page")
        return results

    for a in symptom_list.select("a[href]"):
        # Symptom name
        title_el = a.select_one(".title-md")
        if not title_el:
            continue
        symptom = title_el.get_text(strip=True)
        if not symptom:
            continue

        # Short description blurb
        desc_el = a.select_one("p")
        description = desc_el.get_text(strip=True) if desc_el else ""

        # Percentage of customers who reported this symptom
        pct_el = a.select_one(".symptom-list__reported-by")
        pct_text = pct_el.get_text(strip=True) if pct_el else ""
        pct_reported = 0
        m = re.search(r"(\d+)", pct_text)
        if m:
            pct_reported = int(m.group(1))

        # Absolute URL
        href = a.get("href", "").split("?")[0]
        if href.startswith("/"):
            href = "https://www.partselect.com" + href

        results.append({
            "appliance":    appliance,
            "symptom":      symptom,
            "description":  description,
            "pct_reported": pct_reported,
            "url":          href,
        })

    return results


# Level 2 parser

def _text(el) -> str:
    return el.get_text(separator=" ", strip=True) if el else ""


def parse_symptom_detail(html: str) -> dict:
    """
    Parse a symptom detail page (e.g. /Repair/Refrigerator/Noisy/).

    Actual DOM structure (gotten from DevTools):

      div#main.repair
        h1                              ← page title (skip)
        div[data-yt-init]               ← video wrapper
        div.repair__intro               ← contains difficulty text
        div.symptom-list                ← all part sections live here
          h2.section-title              ← part type name
          div.symptom-list__desc        ← content wrapper
            div.col-lg-6                ← left column: text
              p                        ← part description
              p                        ← "How to inspect..." lead-in (skip)
              ol > li                  ← inspection steps
            div.col-lg-6               ← right column: images (ignore)
          div.row (CTA)                ← "Start Your Repair Here" button (skip)
          h2.section-title             ← next part ...
          ...
          h2 "More Repair Parts"       ← sentinel: stop here

    Returns:
      difficulty       — "EASY" | "REALLY EASY" | "etc"
      video_url        — YouTube URL or ""
      parts            — list of:
        {
          part_type:        str,
          part_description: str,
          inspection_steps: list[str],
        }
    """
    soup = BeautifulSoup(html, "lxml")

    # Difficulty 
    # "Rated as EASY" is a text node inside div.repair__intro
    difficulty = ""
    for text_node in soup.find_all(string=re.compile(r"rated\s+as", re.I)):
        m = re.search(r"rated\s+as\s+([A-Z ]+)", text_node, re.I)
        if m:
            difficulty = re.split(r"\d|\n", m.group(1).strip().upper())[0].strip()
            break

    # Video URL 
    # YouTube video ID lives on data-yt-init of the wrapper div
    video_url = ""
    vid_div = soup.select_one("div[data-yt-init]")
    if vid_div:
        vid_id = vid_div.get("data-yt-init", "").strip()
        if vid_id:
            video_url = f"https://www.youtube.com/watch?v={vid_id}"

    # Per-part sections 
    # All part sections live inside div.symptom-list on the detail page.
    parts = []

    symptom_list = soup.select_one("div.symptom-list")
    if not symptom_list:
        return {"difficulty": difficulty, "video_url": video_url, "parts": parts}

    for h2 in symptom_list.select("h2.section-title"):
        part_type = _text(h2)
        if not part_type:
            continue
        # "More Repair Parts" is the sentinel — everything after is nav/footer
        if "more repair parts" in part_type.lower():
            break

        part_description = ""
        inspection_steps = []

        # The content div is the next sibling div.symptom-list__desc
        desc_wrapper = h2.find_next_sibling("div", class_="symptom-list__desc")
        if not desc_wrapper:
            continue

        # Text lives in the first div.col-lg-6
        text_col = desc_wrapper.select_one("div.col-lg-6")
        if not text_col:
            continue

        # Paragraphs: first non-empty one is the description;
        # any paragraph containing "how to inspect" is just a lead-in header
        for p in text_col.select("p"):
            text = _text(p)
            if not text:
                continue
            if "how to inspect" in text.lower():
                continue  # lead-in, skip
            if not part_description:
                part_description = text

        # Steps from the ordered list
        ol = text_col.select_one("ol")
        if ol:
            inspection_steps = [_text(li) for li in ol.select("li") if _text(li)]

        if part_description or inspection_steps:
            parts.append({
                "part_type":        part_type,
                "part_description": part_description,
                "inspection_steps": inspection_steps,
            })

    return {
        "difficulty": difficulty,
        "video_url":  video_url,
        "parts":      parts,
    }


# DB upsert 

def init_repair_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS repair_guides (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            appliance    TEXT,
            symptom      TEXT,
            description  TEXT,
            pct_reported INTEGER,
            url          TEXT UNIQUE,
            difficulty   TEXT,
            video_url    TEXT,
            parts        TEXT,   -- JSON: [{part_type, part_description, inspection_steps[]}]
            part_types   TEXT    -- JSON: flat list of part type names for quick filtering
        )
    """)


def upsert_repair_guide(guide: dict):
    if not os.path.exists(DB_PATH):
        print("  [db] parts.db not found — skipping DB insert (JSON output still saved)")
        return
    try:
        with sqlite3.connect(DB_PATH) as conn:
            init_repair_table(conn)
            part_types_flat = [p["part_type"] for p in guide.get("parts", [])]
            conn.execute("""
                INSERT OR REPLACE INTO repair_guides
                    (appliance, symptom, description, pct_reported, url,
                     difficulty, video_url, parts, part_types)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                guide["appliance"],
                guide["symptom"],
                guide["description"],
                guide["pct_reported"],
                guide["url"],
                guide.get("difficulty", ""),
                guide.get("video_url", ""),
                json.dumps(guide.get("parts", []),     ensure_ascii=False),
                json.dumps(part_types_flat,             ensure_ascii=False),
            ))
    except Exception as e:
        print(f"  [db error] {e}")


def save_json(guides: list[dict]):
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(guides, f, indent=2, ensure_ascii=False)


# Main 

def main():
    parser = argparse.ArgumentParser(description="PartSelect repair guide scraper")
    parser.add_argument("--dry-run", action="store_true",
                        help="Level 1 only — collect symptom metadata, skip detail pages")
    parser.add_argument("--reset", action="store_true",
                        help="Delete repair_guides.json and start fresh")
    args = parser.parse_args()

    os.makedirs(BASE_DIR, exist_ok=True)

    if args.reset:
        if os.path.exists(OUTPUT_PATH):
            os.remove(OUTPUT_PATH)
            print(f"[reset] Deleted {OUTPUT_PATH}")
        return

    # Resume: load any previously scraped guides
    existing: dict[str, dict] = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            for g in json.load(f):
                existing[g["url"]] = g
        print(f"[resume] {len(existing)} guides already in output file")

    all_guides: list[dict] = list(existing.values())
    seen_urls:  set[str]   = set(existing.keys())

    pw, browser, context, page = make_browser()

    try:
        for listing_url, appliance in REPAIR_PAGES:
            print(f"\n{'='*60}")
            print(f"[level1] {appliance.upper()} — {listing_url}")
            print(f"{'='*60}")

            html = fetch(page, listing_url)
            if not html:
                print("  ✗ failed to fetch listing page, skipping")
                continue

            symptoms = parse_symptom_list(html, appliance)
            print(f"  → {len(symptoms)} symptoms found")
            polite_delay()

            for i, sym in enumerate(symptoms, 1):
                label = f"[{i}/{len(symptoms)}] {sym['symptom']} ({sym['pct_reported']}%)"

                if sym["url"] in seen_urls:
                    print(f"  {label} — already scraped, skipping")
                    continue

                if args.dry_run:
                    print(f"  {label} — dry-run, recording metadata only")
                    all_guides.append(sym)
                    seen_urls.add(sym["url"])
                    continue

                print(f"\n  {label}")
                print(f"    GET {sym['url']}")

                detail_html = fetch(page, sym["url"])
                if not detail_html:
                    print(f"    ✗ failed to fetch detail page, skipping")
                    polite_delay()
                    continue

                detail = parse_symptom_detail(detail_html)
                guide  = {**sym, **detail}

                # Print summary for this guide
                print(
                    f"    ✓ difficulty={guide['difficulty'] or '?'} | "
                    f"video={'yes' if guide['video_url'] else 'no'} | "
                    f"{len(guide['parts'])} part section(s)"
                )
                for p in guide["parts"]:
                    print(f"      · {p['part_type']} — {len(p['inspection_steps'])} steps")

                all_guides.append(guide)
                seen_urls.add(sym["url"])

                upsert_repair_guide(guide)

                # Persist after every guide so a crash loses at most one entry
                save_json(all_guides)

                polite_delay()

    finally:
        page.close()
        context.close()
        browser.close()
        pw.stop()

    # Final save (covers dry-run path too)
    save_json(all_guides)

    print(f"\n{'='*60}")
    print(f"Done. {len(all_guides)} repair guides saved to {OUTPUT_PATH}")
    if os.path.exists(DB_PATH):
        print(f"      repair_guides table updated in {DB_PATH}")


if __name__ == "__main__":
    main()