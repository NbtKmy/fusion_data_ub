#!/usr/bin/env python3
"""
Merge two SQLite databases (same schema) into one output file.
IDs from DB2 are offset by DB1's max IDs to avoid primary-key conflicts.
All foreign-key references are remapped accordingly.
"""

import argparse
import sqlite3
import shutil

DB1_DEFAULT = "to_fuse_sample1.sqlite3"
DB2_DEFAULT = "to_fuse_sample2.sqlite3"
OUTPUT_DEFAULT = "YYYY_MM_DD_fused.sqlite3"


def max_id(conn: sqlite3.Connection, table: str, col: str) -> int:
    result = conn.execute(f'SELECT MAX("{col}") FROM "{table}"').fetchone()[0]
    return result or 0


def merge(db1: str, db2: str, output: str) -> None:
    shutil.copy2(db1, output)
    print(f"Copied {db1} → {output}")

    out = sqlite3.connect(output)
    src = sqlite3.connect(db2)

    # Capture DB1 max IDs (offsets for DB2 rows)
    off_project   = max_id(out, "projects",  "id")
    off_document  = max_id(out, "documents", "id")
    off_tag       = max_id(out, "tags",      "id")
    off_highlight = max_id(out, "highlights","id")
    off_command   = max_id(out, "commands",  "id")

    print(f"DB1 offsets → projects:{off_project}  documents:{off_document}  "
          f"tags:{off_tag}  highlights:{off_highlight}  commands:{off_command}")

    out.execute("PRAGMA foreign_keys = OFF")
    out.execute("BEGIN")

    # 1. users — merge by login (TEXT primary key), skip duplicates
    for row in src.execute("SELECT * FROM users"):
        out.execute("INSERT OR IGNORE INTO users VALUES (?,?,?,?,?,?,?,?)", row)

    # 2. projects — remap id
    project_map: dict[int, int] = {}
    for row in src.execute("SELECT * FROM projects"):
        new_id = row[0] + off_project
        project_map[row[0]] = new_id
        out.execute("INSERT INTO projects VALUES (?,?,?,?)",
                    (new_id, row[1], row[2], row[3]))

    # 3. project_members — remap project_id
    for row in src.execute("SELECT * FROM project_members"):
        out.execute("INSERT OR IGNORE INTO project_members VALUES (?,?,?)",
                    (project_map[row[0]], row[1], row[2]))

    # 4. documents — remap id + project_id
    document_map: dict[int, int] = {}
    for row in src.execute("SELECT * FROM documents"):
        new_id = row[0] + off_document
        document_map[row[0]] = new_id
        out.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)",
                    (new_id, row[1], row[2], row[3], row[4],
                     project_map[row[5]], row[6], row[7]))

    # 5. tags — remap id + project_id
    tag_map: dict[int, int] = {}
    for row in src.execute("SELECT * FROM tags"):
        new_id = row[0] + off_tag
        tag_map[row[0]] = new_id
        out.execute("INSERT INTO tags VALUES (?,?,?,?)",
                    (new_id, project_map[row[1]], row[2], row[3]))

    # 6. highlights — remap id + document_id
    highlight_map: dict[int, int] = {}
    for row in src.execute("SELECT * FROM highlights"):
        new_id = row[0] + off_highlight
        highlight_map[row[0]] = new_id
        out.execute("INSERT INTO highlights VALUES (?,?,?,?,?)",
                    (new_id, document_map[row[1]], row[2], row[3], row[4]))

    # 7. highlight_tags — remap both FK columns
    for row in src.execute("SELECT * FROM highlight_tags"):
        out.execute("INSERT OR IGNORE INTO highlight_tags VALUES (?,?)",
                    (highlight_map[row[0]], tag_map[row[1]]))

    # 8. commands — remap id, project_id, document_id (document_id may be NULL)
    for row in src.execute("SELECT * FROM commands"):
        new_did = document_map[row[4]] if row[4] is not None else None
        out.execute("INSERT INTO commands VALUES (?,?,?,?,?,?)",
                    (row[0] + off_command, row[1], row[2],
                     project_map[row[3]], new_did, row[5]))

    # 9. Update sqlite_sequence so future autoincrement works correctly
    for table, col in [("projects", "id"), ("documents", "id"), ("tags", "id"),
                       ("highlights", "id"), ("commands", "id")]:
        new_max = max_id(out, table, col)
        out.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = ?", (new_max, table))

    out.execute("COMMIT")
    out.close()
    src.close()

    # Verify row counts
    verify = sqlite3.connect(output)
    print("\nRow counts in merged database:")
    for table in ("projects", "users", "documents", "tags",
                  "highlights", "highlight_tags", "commands", "project_members"):
        n = verify.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        print(f"  {table:<18} {n}")
    verify.close()
    print(f"\nDone → {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Merge two SQLite databases with identical schemas into one output file."
    )
    parser.add_argument("db1", nargs="?", default=DB1_DEFAULT,
                        help=f"First (base) SQLite file (default: {DB1_DEFAULT})")
    parser.add_argument("db2", nargs="?", default=DB2_DEFAULT,
                        help=f"Second SQLite file to merge in (default: {DB2_DEFAULT})")
    parser.add_argument("-o", "--output", default=OUTPUT_DEFAULT,
                        help=f"Output SQLite file (default: {OUTPUT_DEFAULT})")
    args = parser.parse_args()
    merge(args.db1, args.db2, args.output)
