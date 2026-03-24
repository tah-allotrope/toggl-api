"""Apply the pending SQL migrations directly to the hosted Supabase database."""

import os
import sys
from pathlib import Path

import psycopg


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.env_utils import get_postgres_url


MIGRATION_FILES = [
    "supabase/migrations/20260318_000003_views_and_rpc.sql",
    "supabase/migrations/20260322_000004_time_entry_canonical_key.sql",
]


def main() -> int:
    conn = psycopg.connect(get_postgres_url())
    try:
        with conn.cursor() as cur:
            for relative_path in MIGRATION_FILES:
                sql = Path(relative_path).read_text(encoding="utf-8")
                cur.execute(sql)
                print(f"Applied {relative_path}")
        conn.commit()
        print("Hosted Supabase migrations applied successfully")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
