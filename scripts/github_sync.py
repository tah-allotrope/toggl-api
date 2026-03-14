"""GitHub Actions wrapper for running Toggl sync into Firestore."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore


def _load_functions_modules() -> None:
    root = Path(__file__).resolve().parents[1]
    functions_dir = root / "functions"
    if str(functions_dir) not in sys.path:
        sys.path.insert(0, str(functions_dir))


def _init_firestore() -> firestore.Client:
    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if not service_account_json:
        raise ValueError("FIREBASE_SERVICE_ACCOUNT_JSON is required")

    try:
        service_account_info = json.loads(service_account_json)
    except json.JSONDecodeError as exc:
        raise ValueError("FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc

    if not firebase_admin._apps:
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred)

    return firestore.client()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Toggl sync from CI")
    parser.add_argument(
        "--type",
        required=True,
        choices=["quick", "full", "enriched"],
        help="Sync mode to execute",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Year for enriched sync mode",
    )
    parser.add_argument(
        "--earliest-year",
        type=int,
        default=2017,
        help="Earliest year for full sync mode",
    )
    args = parser.parse_args()

    toggl_token = os.getenv("TOGGL_API_TOKEN", "").strip()
    if not toggl_token:
        raise ValueError("TOGGL_API_TOKEN is required")

    _load_functions_modules()

    from sync_engine import sync_current_year, sync_enriched_year, sync_full
    from toggl_client import TogglClient

    db = _init_firestore()
    client = TogglClient(api_token=toggl_token)

    if args.type == "quick":
        result = sync_current_year(client, db)
        print(
            f"quick sync complete year={result.get('year')} entries={result.get('entries', 0)}"
        )
        return

    if args.type == "full":
        result = sync_full(client, db, earliest_year=args.earliest_year)
        print(
            "full sync complete "
            f"years={result.get('years_synced', 0)} "
            f"entries={result.get('total_entries', 0)}"
        )
        return

    if args.year is None:
        raise ValueError("--year is required when --type=enriched")

    result = sync_enriched_year(client, db, args.year)
    print(
        f"enriched sync complete year={result.get('year')} entries={result.get('entries', 0)}"
    )


if __name__ == "__main__":
    main()
