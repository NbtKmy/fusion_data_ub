# fusion_data_ub

Merges two SQLite databases that share an identical schema into a single output file.
IDs from the second database are offset by the maximum IDs of the first, so all primary keys and foreign key references remain consistent in the merged result.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (recommended) — or any standard Python environment

No third-party packages are required. The script uses only the Python standard library (`sqlite3`, `shutil`, `argparse`).

## Setup

```bash
# Clone / enter the project directory, then install with uv
uv sync
```

## Usage

```
uv run python main.py [db1] [db2] [-o OUTPUT]
```

| Argument | Description |
|---|---|
| `db1` | First (base) SQLite file. Its data is copied as-is. |
| `db2` | Second SQLite file. Its rows are merged in with remapped IDs. |
| `-o`, `--output` | Path of the output file to create. |

All three arguments are optional and fall back to the default filenames if omitted.

### Examples

**Run with defaults** (uses the hardcoded filenames in the script):
```bash
uv run python main.py
```

**Specify both input files, use the default output name:**
```bash
uv run python main.py database_a.sqlite3 database_b.sqlite3
```

**Specify everything:**
```bash
uv run python main.py database_a.sqlite3 database_b.sqlite3 -o merged.sqlite3
```

**Show help:**
```bash
uv run python main.py --help
```

## How it works

1. `db1` is copied verbatim to the output path — this becomes the base.
2. The maximum ID of each auto-increment table in `db1` is recorded as an offset.
3. Every row from `db2` is inserted into the output with its IDs shifted by the offset:
   - `projects`, `documents`, `tags`, `highlights`, `commands` — primary keys and all foreign key references are remapped.
   - `users` — merged by login (text primary key); duplicates are silently skipped.
   - `project_members`, `highlight_tags` — junction tables are remapped using the new IDs.
4. `sqlite_sequence` is updated so future `AUTOINCREMENT` operations continue from the correct values.
5. The entire operation runs inside a single transaction with `PRAGMA foreign_keys = OFF` to allow temporary referential inconsistencies during the merge.

## Output

After a successful run the script prints a row-count summary, for example:

```
Copied database_a.sqlite3 → merged.sqlite3
DB1 offsets → projects:1  documents:10  tags:97  highlights:308  commands:537

Row counts in merged database:
  projects           2
  users              1
  documents          24
  tags               194
  highlights         1063
  highlight_tags     1435
  commands           2035
  project_members    2

Done → merged.sqlite3
```
