import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("leave_management_system.db")


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r["name"] for r in cur.fetchall()]
    print("Tables:", tables)

    print("\nTables with username/password columns:")
    for t in tables:
        try:
            cur.execute(f"PRAGMA table_info({t})")
            cols = [r["name"] for r in cur.fetchall()]
            if "username" in cols and "password" in cols:
                print("-", t)
        except Exception:
            pass

    # Try finding an admin record anywhere
    print("\nSearching for username='admin' in username/password tables:")
    for t in tables:
        try:
            cur.execute(f"PRAGMA table_info({t})")
            cols = [r["name"] for r in cur.fetchall()]
            if "username" in cols and "password" in cols:
                cur.execute(f"SELECT * FROM {t} WHERE username=? LIMIT 1", ("admin",))
                row = cur.fetchone()
                if row:
                    print("Found in", t, dict(row))
        except Exception:
            pass

    con.close()


if __name__ == "__main__":
    main()

