"""Run a provenance-preserving full-text query against the agent SQLite database."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("query", help="SQLite FTS5 query, e.g. 城市更新 AND 实施方案")
    parser.add_argument("--district", default="", help="Prioritise this administrative district")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    con = sqlite3.connect(f"file:{args.database.resolve().as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    params = [args.query]
    district_boost = "CASE WHEN d.jurisdiction_name=? THEN 0 WHEN d.jurisdiction_name='北京市' THEN 1 WHEN d.jurisdiction_level='national' THEN 2 WHEN d.jurisdiction_name LIKE '北京市%' THEN 3 ELSE 4 END"
    params.append(args.district or "__no_district__")
    params.append(args.limit)
    rows = con.execute(
        f"""SELECT d.title,d.document_type,d.evidence_tier,d.jurisdiction_name,d.published_date,
                   d.issuing_authority,d.official_url,d.original_path,
                   snippet(documents_fts, 2, '<b>', '</b>', ' … ', 28) AS excerpt
            FROM documents_fts JOIN documents d ON d.rowid=documents_fts.rowid
            WHERE documents_fts MATCH ?
            ORDER BY {district_boost}, bm25(documents_fts)
            LIMIT ?""",
        params,
    ).fetchall()
    for row in rows:
        print("\n".join(f"{key}: {row[key]}" for key in row.keys()))
        print("---")


if __name__ == "__main__":
    main()
