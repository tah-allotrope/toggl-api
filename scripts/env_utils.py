"""Helpers for loading local environment variables used by sync scripts."""

import os

from dotenv import load_dotenv


load_dotenv()


def get_postgres_url() -> str:
    """Return the configured Postgres connection URL."""
    db_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError(
            "SUPABASE_DB_URL or DATABASE_URL environment variable is required"
        )
    return db_url


def get_toggl_token() -> str:
    """Return the configured Toggl API token."""
    token = os.environ.get("TOGGL_API_TOKEN")
    if not token:
        raise ValueError("TOGGL_API_TOKEN environment variable is required")
    return token
