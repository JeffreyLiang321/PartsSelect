import sqlite3
from contextlib import contextmanager
from backend.config import DB_PATH

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# standard PS format
def get_part(part_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM parts WHERE part_id = ?",
            (part_id,)
        ).fetchone()
        return dict(row) if row else None

def get_part_by_mpn(mpn: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM parts WHERE mpn_id = ?",
            (mpn,)
        ).fetchall()
        if rows:
            return [dict(r) for r in rows]

        # Fallback — old/discontinued MPN, find what supersedes it if any
        rows = conn.execute(
            "SELECT * FROM parts WHERE replace_parts LIKE ?",
                (f"%{mpn}%",)
            ).fetchall()
        return [dict(r) for r in rows]

def check_compatibility(part_id: str, model_number: str) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM parts WHERE part_id = ?",
            (part_id,)
        ).fetchone()

    if not row:
        return {"compatible": False, "reason": "Part not found", "confidence": "exact"}

    models = [m.strip().upper() for m in row["compatible_models"].split("|")]
    compatible = model_number.strip().upper() in models

    return {
        **dict(row),
        "compatible": compatible,
        "reason":     "Found in compatibility list" if compatible else "Not in compatibility list",
        "confidence": "exact"
    }

def search_by_model(model_number: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT part_id, part_name, part_price, brand,
               appliance_type, image_url, in_stock, rating
               FROM parts WHERE compatible_models LIKE ?
               ORDER BY rating DESC LIMIT 10""",
            (f"%{model_number}%",)
        ).fetchall()
    return [dict(r) for r in rows]

def get_install_guide(part_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            """SELECT part_id, part_name, install_difficulty,
               install_time, install_video_url, description
               FROM parts WHERE part_id = ?""",
            (part_id,)
        ).fetchone()
    return dict(row) if row else None

def find_replacement_parts(part_id: str, mpn_id: str, replace_parts_str: str) -> list[dict]:
    old_numbers = [n.strip() for n in replace_parts_str.replace("|", ",").split(",") if n.strip()]
    
    # Include the part's own MPN as a search term
    search_terms = ([mpn_id] if mpn_id else []) + old_numbers
    
    if not search_terms:
        return []
    
    conditions = " OR ".join(["replace_parts LIKE ?"] * len(search_terms))
    params = [f"%{t}%" for t in search_terms] + [part_id]
    
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM parts WHERE ({conditions}) AND part_id != ? LIMIT 5",
            params
        ).fetchall()
    
    return [dict(r) for r in rows]