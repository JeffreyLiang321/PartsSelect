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

def get_part(part_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM parts WHERE part_id = ?",
            (part_id,)
        ).fetchone()
        return dict(row) if row else None

def check_compatibility(part_id: str, model_number: str) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT part_id, part_name, compatible_models FROM parts WHERE part_id = ?",
            (part_id,)
        ).fetchone()

    if not row:
        return {"compatible": False, "reason": "Part not found", "confidence": "exact"}

    models = [m.strip().upper() for m in row["compatible_models"].split("|")]
    compatible = model_number.strip().upper() in models

    return {
        "compatible":  compatible,
        "part_name":   row["part_name"],
        "part_id":     row["part_id"],
        "reason":      "Found in compatibility list" if compatible else "Not in compatibility list",
        "confidence":  "exact"
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