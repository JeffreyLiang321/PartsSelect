"""
SQLite schema and insert helpers.
Database lives at data/parts.db relative to repo root.
"""

import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "parts.db")


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS parts (
                ps_number           TEXT PRIMARY KEY,
                mfr_part_number     TEXT,
                brand               TEXT,
                appliance_type      TEXT,   -- 'refrigerator' | 'dishwasher'
                part_type           TEXT,   -- e.g. 'Ice Maker', 'Pump & Motor'
                name                TEXT,
                description         TEXT,
                price               REAL,
                in_stock            INTEGER,  -- 1 | 0
                symptoms_fixed      TEXT,     -- JSON array of strings
                installation_notes  TEXT,
                compatible_models   TEXT,     -- JSON array of model numbers
                image_url           TEXT,
                product_url         TEXT,
                rating              REAL,
                review_count        INTEGER
            );

            CREATE TABLE IF NOT EXISTS repair_guides (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                appliance   TEXT,   -- 'refrigerator' | 'dishwasher'
                symptom     TEXT,
                steps       TEXT,   -- JSON array of step strings
                part_types  TEXT    -- JSON array of implicated part types
            );
        """)
    print(f"[db] Initialized at {DB_PATH}")


def upsert_part(part: dict):
    """Insert or replace a part record. Serializes list fields to JSON."""
    for field in ("symptoms_fixed", "compatible_models"):
        if isinstance(part.get(field), list):
            part[field] = json.dumps(part[field])

    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO parts (
                ps_number, mfr_part_number, brand, appliance_type, part_type,
                name, description, price, in_stock, symptoms_fixed,
                installation_notes, compatible_models, image_url, product_url,
                rating, review_count
            ) VALUES (
                :ps_number, :mfr_part_number, :brand, :appliance_type, :part_type,
                :name, :description, :price, :in_stock, :symptoms_fixed,
                :installation_notes, :compatible_models, :image_url, :product_url,
                :rating, :review_count
            )
        """, part)


def already_scraped(ps_number: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM parts WHERE ps_number = ?", (ps_number,)
        ).fetchone()
    return row is not None


def count_parts() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
