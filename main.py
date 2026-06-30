#!/usr/bin/env python3
"""
Merge two Taguette SQLite databases into one output file.
Tags are deduplicated by path; document names get a suffix on conflict.
"""

import argparse
import sqlite3
import shutil

DB1_DEFAULT = "to_fuse_sample1.sqlite3"
DB2_DEFAULT = "to_fuse_sample2.sqlite3"
OUTPUT_DEFAULT = "YYYY_MM_DD_fused.sqlite3"


def merge(db1: str, db2: str, output: str) -> None:
    shutil.copy2(db1, output)
    print(f"Copied {db1} → {output}")

    con = sqlite3.connect(output)
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()

    cur.execute("ATTACH DATABASE ? AS incoming", (db2,))

    base_project_id = cur.execute(
        "SELECT id FROM projects ORDER BY id LIMIT 1"
    ).fetchone()[0]
    incoming_project_id = cur.execute(
        "SELECT id FROM incoming.projects ORDER BY id LIMIT 1"
    ).fetchone()[0]

    # 1. Tags — insert missing paths, build incoming→base id mapping
    cur.execute("""
        INSERT INTO tags (project_id, path, description)
        SELECT ?, t.path, t.description
        FROM incoming.tags t
        WHERE t.project_id = ?
          AND NOT EXISTS (
              SELECT 1 FROM tags b
              WHERE b.project_id = ? AND b.path = t.path
          )
    """, (base_project_id, incoming_project_id, base_project_id))

    cur.execute("DROP TABLE IF EXISTS temp.tag_map")
    cur.execute("""
        CREATE TEMP TABLE tag_map AS
        SELECT it.id AS incoming_tag_id, bt.id AS base_tag_id
        FROM incoming.tags it
        JOIN tags bt ON bt.project_id = ? AND bt.path = it.path
        WHERE it.project_id = ?
    """, (base_project_id, incoming_project_id))

    # 2. Documents — append "(importiert)" on name conflict
    cur.execute("DROP TABLE IF EXISTS temp.doc_map")
    cur.execute("""
        CREATE TEMP TABLE doc_map (
            incoming_doc_id INTEGER,
            base_doc_id     INTEGER
        )
    """)

    for row in cur.execute("""
        SELECT id, name, description, filename, created, text_direction, contents
        FROM incoming.documents
        WHERE project_id = ?
        ORDER BY id
    """, (incoming_project_id,)).fetchall():
        old_id, name, description, filename, created, text_direction, contents = row

        count = cur.execute("""
            SELECT COUNT(*) FROM documents
            WHERE project_id = ? AND name = ?
        """, (base_project_id, name)).fetchone()[0]
        new_name = name if count == 0 else f"{name} (importiert)"

        cur.execute("""
            INSERT INTO documents
                (name, description, filename, created, project_id, text_direction, contents)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (new_name, description, filename, created, base_project_id, text_direction, contents))

        cur.execute("INSERT INTO temp.doc_map VALUES (?, ?)", (old_id, cur.lastrowid))

    # 3. Highlights — remap document_id via doc_map
    cur.execute("DROP TABLE IF EXISTS temp.hl_map")
    cur.execute("""
        CREATE TEMP TABLE hl_map (
            incoming_highlight_id INTEGER,
            base_highlight_id     INTEGER
        )
    """)

    for row in cur.execute("""
        SELECT id, document_id, start_offset, end_offset, snippet
        FROM incoming.highlights
        ORDER BY id
    """).fetchall():
        old_hl_id, old_doc_id, start_offset, end_offset, snippet = row

        mapping = cur.execute(
            "SELECT base_doc_id FROM temp.doc_map WHERE incoming_doc_id = ?",
            (old_doc_id,)
        ).fetchone()
        if mapping is None:
            continue

        cur.execute("""
            INSERT INTO highlights (document_id, start_offset, end_offset, snippet)
            VALUES (?, ?, ?, ?)
        """, (mapping[0], start_offset, end_offset, snippet))

        cur.execute("INSERT INTO temp.hl_map VALUES (?, ?)", (old_hl_id, cur.lastrowid))

    # 4. Highlight-tags — remap through both maps
    cur.execute("""
        INSERT OR IGNORE INTO highlight_tags (highlight_id, tag_id)
        SELECT hm.base_highlight_id, tm.base_tag_id
        FROM incoming.highlight_tags iht
        JOIN temp.hl_map  hm ON hm.incoming_highlight_id = iht.highlight_id
        JOIN temp.tag_map tm ON tm.incoming_tag_id        = iht.tag_id
    """)

    con.commit()
    cur.execute("DETACH DATABASE incoming")

    print("\nRow counts in merged database:")
    for table in ("projects", "users", "documents", "tags",
                  "highlights", "highlight_tags", "commands", "project_members"):
        n = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        print(f"  {table:<18} {n}")

    con.close()
    print(f"\nDone → {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Merge two Taguette SQLite databases into one output file."
    )
    parser.add_argument("db1", nargs="?", default=DB1_DEFAULT,
                        help=f"Base SQLite file (default: {DB1_DEFAULT})")
    parser.add_argument("db2", nargs="?", default=DB2_DEFAULT,
                        help=f"Incoming SQLite file to merge in (default: {DB2_DEFAULT})")
    parser.add_argument("-o", "--output", default=OUTPUT_DEFAULT,
                        help=f"Output SQLite file (default: {OUTPUT_DEFAULT})")
    args = parser.parse_args()
    merge(args.db1, args.db2, args.output)
