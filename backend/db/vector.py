# backend/db/vector.py
"""
Semantic search layer — all vector retrieval lives here.

Uses ChromaDB for persistence, matching the setup in csv_to_sqlite.py.
Three collections:
  parts          — built by csv_to_sqlite.py (already exists after migration)
  repair_guides  — built here on first call from repair_guides.json
  blogs          — built here on first call from blogs.json

Embedding model: text-embedding-3-small (OpenAI), same as csv_to_sqlite.py.

Lazy initialisation: collections are loaded/built on first query, not at
import time. This means a cold start on first request takes a few seconds
(embedding build) but restarts are instant (loading from disk).

Functions exported (called by rag_mcp.py):
  semantic_search(symptom, appliance_type)  → list of full part dicts
  search_repair_guide(symptom, appliance_type) → repair guide dict
  search_blogs(query)                       → list of {title, url}
"""

import os
import json
import chromadb
from openai import OpenAI

# ── Paths ─────────────────────────────────────────────────────────────────────

_BASE_DIR     = os.path.join(os.path.dirname(__file__), "..", "..", "data")
_CHROMA_PATH  = os.path.join(_BASE_DIR, "chroma")
_REPAIRS_PATH = os.path.join(_BASE_DIR, "repair_guides.json")
_BLOGS_PATH   = os.path.join(_BASE_DIR, "blogs.json")

# ── Clients ───────────────────────────────────────────────────────────────────

_openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
_chroma_client = chromadb.PersistentClient(path=_CHROMA_PATH)

# ── Module-level collection handles (populated lazily) ────────────────────────
# None until first query — avoids slow startup on import.

_parts_col   = None
_repairs_col = None
_blogs_col   = None


# ── Embedding ─────────────────────────────────────────────────────────────────

def _embed(text: str) -> list[float]:
    response = _openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


# ── Collection loaders ────────────────────────────────────────────────────────

def _get_parts_collection():
    """
    Load the parts ChromaDB collection built by csv_to_sqlite.py.
    Raises clearly if the migration hasn't been run yet.
    """
    global _parts_col
    if _parts_col is not None:
        return _parts_col

    try:
        _parts_col = _chroma_client.get_collection("parts")
        print(f"[vector] Loaded parts collection ({_parts_col.count()} docs)")
    except Exception:
        raise RuntimeError(
            "Parts ChromaDB collection not found. "
            "Run `python scraper/csv_to_sqlite.py` first to build it."
        )
    return _parts_col


def _get_repairs_collection():
    """
    Load or build the repair_guides ChromaDB collection.

    Each document is: "{symptom} {description} {part_types_flat}"
    Metadata includes everything needed to reconstruct the full guide.
    """
    global _repairs_col
    if _repairs_col is not None:
        return _repairs_col

    col = _chroma_client.get_or_create_collection(
        name="repair_guides",
        metadata={"hnsw:space": "cosine"},
    )

    # Already populated — load and return
    if col.count() > 0:
        print(f"[vector] Loaded repair_guides collection ({col.count()} docs)")
        _repairs_col = col
        return _repairs_col

    # First run — build from repair_guides.json
    print("[vector] Building repair_guides collection from repair_guides.json ...")
    if not os.path.exists(_REPAIRS_PATH):
        raise FileNotFoundError(
            f"repair_guides.json not found at {_REPAIRS_PATH}. "
            "Run scraper/scrape_repairs.py first."
        )

    with open(_REPAIRS_PATH, "r", encoding="utf-8") as f:
        guides = json.load(f)

    ids, embeddings, documents, metadatas = [], [], [], []

    for guide in guides:
        # Text to embed: symptom + description + flat list of part type names
        part_types_flat = ", ".join(
            p["part_type"] for p in guide.get("parts", [])
        )
        text = " ".join(filter(None, [
            guide.get("symptom", ""),
            guide.get("description", ""),
            part_types_flat,
        ]))

        doc_id = f"{guide['appliance']}_{guide['symptom'].replace(' ', '_').lower()}"

        ids.append(doc_id)
        embeddings.append(_embed(text))
        documents.append(text)
        metadatas.append({
            "appliance":    guide["appliance"],
            "symptom":      guide["symptom"],
            "description":  guide.get("description", ""),
            "difficulty":   guide.get("difficulty", ""),
            "video_url":    guide.get("video_url", ""),
            "url":          guide.get("url", ""),
            # Store parts as JSON string b/c ChromaDB metadata must be scalar
            "parts_json":   json.dumps(guide.get("parts", [])),
        })

    col.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    print(f"[vector] Built repair_guides collection — {len(ids)} guides embedded")
    _repairs_col = col
    return _repairs_col


def _get_blogs_collection():
    """
    Load or build the blogs ChromaDB collection.
    Each document is the blog title — that's all we have and all we need.
    """
    global _blogs_col
    if _blogs_col is not None:
        return _blogs_col

    col = _chroma_client.get_or_create_collection(
        name="blogs",
        metadata={"hnsw:space": "cosine"},
    )

    if col.count() > 0:
        print(f"[vector] Loaded blogs collection ({col.count()} docs)")
        _blogs_col = col
        return _blogs_col

    print("[vector] Building blogs collection from blogs.json ...")
    if not os.path.exists(_BLOGS_PATH):
        raise FileNotFoundError(
            f"blogs.json not found at {_BLOGS_PATH}. "
            "Run scraper/scrape_blogs.py first."
        )

    with open(_BLOGS_PATH, "r", encoding="utf-8") as f:
        blogs = json.load(f)

    ids, embeddings, documents, metadatas = [], [], [], []

    for i, blog in enumerate(blogs):
        title = blog.get("title", "").strip()
        url   = blog.get("url", "").strip()
        if not title or not url:
            continue

        ids.append(f"blog_{i}")
        embeddings.append(_embed(title))
        documents.append(title)
        metadatas.append({"title": title, "url": url})

    col.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    print(f"[vector] Built blogs collection — {len(ids)} posts embedded")
    _blogs_col = col
    return _blogs_col


# ── Public search functions ───────────────────────────────────────────────────

def semantic_search(symptom: str, appliance_type: str, k: int = 5) -> list[dict]:
    """
    Find parts that fix a described symptom.

    Queries the parts ChromaDB collection with an appliance_type filter,
    then enriches each hit with the full SQL record from client.get_part().
    2-step pattern means ChromaDB handles retrieval and SQLite stays
    the source of truth for complete part data.

    Returns list of full part dicts, cosine similarity rank.
    """
    # Importing here to avoid circular imports
    # client.py is SQL only, doesn't need vector.py
    from backend.db.client import get_part

    col = _get_parts_collection()

    results = col.query(
        query_embeddings=[_embed(symptom)],
        n_results=k,
        where={"appliance_type": appliance_type},
        include=["metadatas", "distances"],
    )

    parts = []
    seen  = set()

    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for meta, distance in zip(metadatas, distances):
        part_id = meta.get("part_id")
        if not part_id or part_id in seen:
            continue
        seen.add(part_id)

        # Enrich with full record from SQLite
        full_part = get_part(part_id)
        if full_part:
            # Attach similarity score so caller can see ranking signal
            full_part["similarity_score"] = round(1 - distance, 4)
            parts.append(full_part)

    return parts


def search_repair_guide(symptom: str, appliance_type: str) -> dict | None:
    """
    Find the closest repair guide for a described symptom.

    Filters by appliance_type and returns the top match.
    The returned dict includes the full parts list with per-part
    descriptions and inspection steps.
    """
    col = _get_repairs_collection()

    results = col.query(
        query_embeddings=[_embed(symptom)],
        n_results=3,
        where={"appliance": appliance_type},
        include=["metadatas", "distances"],
    )

    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if not metadatas:
        return None

    # Return the top match with full parts JSON deserialised
    top = metadatas[0]
    return {
        "appliance":   top["appliance"],
        "symptom":     top["symptom"],
        "description": top["description"],
        "difficulty":  top["difficulty"],
        "video_url":   top["video_url"],
        "url":         top["url"],
        "parts":       json.loads(top.get("parts_json", "[]")),
        "similarity_score": round(1 - distances[0], 4),
    }


def search_blogs(query: str, k: int = 3) -> list[dict]:
    """
    Find blog posts relevant to a query by semantic similarity over titles.

    Returns list of {title, url} dicts ranked by relevance.
    Caller (rag_mcp) is responsible for only surfacing these for
    in-scope refrigerator/dishwasher topics per the system prompt rules.
    """
    col = _get_blogs_collection()

    results = col.query(
        query_embeddings=[_embed(query)],
        n_results=k,
        include=["metadatas", "distances"],
    )

    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    return [
        {
            "title": meta["title"],
            "url":   meta["url"],
            "similarity_score": round(1 - distance, 4),
        }
        for meta, distance in zip(metadatas, distances)
        if meta.get("title") and meta.get("url")
    ]