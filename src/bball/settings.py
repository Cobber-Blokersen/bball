from __future__ import annotations

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "sqlite"
DB_PATH = DATA_DIR / "bball.sqlite3"


def ensure_db_dir() -> None:
    """Ensure the database directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
