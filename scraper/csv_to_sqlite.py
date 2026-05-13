"""
Migrate parts.csv → parts.db (SQLite) once scraping is complete.

Usage:
    python scraper/csv_to_sqlite.py

Run this after the scraper finishes. Safe to run multiple times —
uses INSERT OR REPLACE so duplicates are handled cleanly.
"""

import csv
import os
import sqlite3
import chromadb
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CSV_PATH = os.path.join(BASE_DIR, "parts.csv")
DB_PATH  = os.path.join(BASE_DIR, "parts.db")

# ChromaDB lives next to my SQLite db
CHROMA_PATH = os.path.join(BASE_DIR, "chroma")

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def get_embedding(text: str) -> list[float]:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

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
    """)

def migrate():
    if not os.path.exists(CSV_PATH):
        print(f"✗ {CSV_PATH} not found")
        return

    # SQLite setup
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    # ChromaDB setup — one collection for semantic search
    chroma = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = chroma.get_or_create_collection(
        name="parts",
        metadata={"hnsw:space": "cosine"}
    )

    inserted = 0
    skipped  = 0
    embedded = 0

    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # SQLite insert (same as before) 
                price        = float(row["part_price"])  if row.get("part_price")  else None
                rating       = float(row["rating"])      if row.get("rating")      else None
                review_count = int(row["review_count"])  if row.get("review_count") else 0
                in_stock     = int(row["in_stock"])      if row.get("in_stock")    else 0

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

                # ChromaDB embed (symptoms + description)
                symptoms    = row.get("symptoms", "")
                description = row.get("description", "")
                text_to_embed = " ".join(filter(None, [row.get("part_name", ""),
                                                       row.get("symptoms", ""),
                                                       row.get("description", "")])).strip()

                if text_to_embed and row.get("part_id"):
                    embedding = get_embedding(text_to_embed)
                    collection.upsert(
                        ids=[row["part_id"]],
                        embeddings=[embedding],
                        documents=[text_to_embed],
                        metadatas=[{
                            "part_id":      row["part_id"],
                            "part_name":    row.get("part_name", ""),
                            "appliance_type": row.get("appliance_type", ""),
                            "brand":        row.get("brand", ""),
                            "part_price":   str(price or ""),
                            "image_url":    row.get("image_url", ""),
                            "in_stock":     str(in_stock),
                        }]
                    )
                    embedded += 1
                    if embedded % 100 == 0:
                        print(f"  embedded {embedded} parts...")

            except Exception as e:
                print(f"  skipped {row.get('part_id', '?')}: {e}")
                skipped += 1

    conn.commit()
    conn.close()

    print(f"✓ SQLite: {inserted} parts inserted, {skipped} skipped")
    print(f"✓ ChromaDB: {embedded} parts embedded")
    print(f"✓ Vector store at {CHROMA_PATH}")

if __name__ == "__main__":
    migrate()