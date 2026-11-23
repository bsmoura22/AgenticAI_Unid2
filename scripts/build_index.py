"""Constrói o índice Chroma a partir de data/docs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.rag import CHROMA_DIR, build_store

if __name__ == "__main__":
    store = build_store()
    n = len(store.get()["ids"] or [])
    print(f"OK — {n} chunks em {CHROMA_DIR}")
