"""
Migrate parts.csv → parts.db (SQLite) once scraping is complete.

Usage:
    python scraper/csv_to_sqlite.py

Run this after the scraper finishes. Safe to run multiple times —
uses INSERT OR REPLACE so duplicates are handled cleanly.
"""

import csv
import json
import os
import sqlite3

BASE_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
CSV_PATH  = os.path.join(BASE_DIR, "parts.csv")
DB_PATH   = os.path.join(BASE_DIR, "parts.db")


def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS parts (
            part_id             TEXT PRIMARY KEY,
            part_name           TEXT,
            mpn_id              TEXT,
            part_price          REAL,
            install_difficulty  TEXT,
            install_time        TEXT,
            symptoms            TEXT,
            appliance_types     TEXT,
            replace_parts       TEXT,
            brand               TEXT,
            availability        TEXT,
            in_stock            INTEGER,
            install_video_url   TEXT,
            product_url         TEXT,
            appliance_type      TEXT,
            description         TEXT,
            compatible_models   TEXT,
            image_url           TEXT,
            rating              REAL,
            review_count        INTEGER
        );

        CREATE TABLE IF NOT EXISTS repair_guides (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            appliance   TEXT,
            symptom     TEXT,
            steps       TEXT,
            part_types  TEXT
        );

        CREATE TABLE IF NOT EXISTS blog_posts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT,
            url             TEXT UNIQUE,
            appliance_type  TEXT,
            content         TEXT
        );
    """)


def migrate():
    if not os.path.exists(CSV_PATH):
        print(f"✗ {CSV_PATH} not found — run the scraper first")
        return

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    inserted = 0
    skipped  = 0

    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                price = float(row["part_price"]) if row.get("part_price") else None
                rating = float(row["rating"]) if row.get("rating") else None
                review_count = int(row["review_count"]) if row.get("review_count") else 0
                in_stock = int(row["in_stock"]) if row.get("in_stock") else 0

                conn.execute("""
                    INSERT OR REPLACE INTO parts VALUES (
                        :part_id, :part_name, :mpn_id, :part_price,
                        :install_difficulty, :install_time, :symptoms,
                        :appliance_types, :replace_parts, :brand,
                        :availability, :in_stock, :install_video_url,
                        :product_url, :appliance_type, :description,
                        :compatible_models, :image_url, :rating, :review_count
                    )
                """, {
                    **row,
                    "part_price":   price,
                    "rating":       rating,
                    "review_count": review_count,
                    "in_stock":     in_stock,
                })
                inserted += 1
            except Exception as e:
                print(f"  skipped row {row.get('part_id', '?')}: {e}")
                skipped += 1

    conn.commit()
    conn.close()

    print(f"✓ Migrated {inserted} parts to {DB_PATH}")
    if skipped:
        print(f"  {skipped} rows skipped due to errors")

    # Verify
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
    conn.close()
    print(f"✓ parts.db now has {count} rows")


if __name__ == "__main__":
    migrate()
