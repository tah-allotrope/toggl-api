"""Check local Toggl and Supabase environment readiness."""

import os
import socket
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.env_utils import get_postgres_url


load_dotenv()


def _print_result(label: str, ok: bool, detail: str) -> None:
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {label}: {detail}")


def _check_toggl_token() -> bool:
    token = os.environ.get("TOGGL_API_TOKEN", "")
    if token:
        _print_result("TOGGL_API_TOKEN", True, "present")
        return True
    _print_result("TOGGL_API_TOKEN", False, "missing from .env or process environment")
    return False


def _check_supabase_http_env() -> bool:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")
    if not url:
        _print_result("SUPABASE_URL", False, "missing from .env or process environment")
        return False
    if not key:
        _print_result(
            "SUPABASE key",
            False,
            "missing SUPABASE_KEY and SUPABASE_ANON_KEY from .env or process environment",
        )
        return False
    _print_result("SUPABASE_URL", True, url)
    _print_result("SUPABASE key", True, "present")
    return True


def _check_dns(hostname: str) -> bool:
    try:
        socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        _print_result("DNS", False, f"{hostname} does not resolve ({exc})")
        return False
    _print_result("DNS", True, f"{hostname} resolves")
    return True


def _check_tcp(hostname: str, port: int) -> bool:
    try:
        with socket.create_connection((hostname, port), timeout=5):
            pass
    except OSError as exc:
        _print_result("TCP", False, f"cannot connect to {hostname}:{port} ({exc})")
        return False
    _print_result("TCP", True, f"can connect to {hostname}:{port}")
    return True


def _check_database_url() -> bool:
    try:
        db_url = get_postgres_url()
    except ValueError as exc:
        _print_result("DATABASE_URL", False, str(exc))
        return False

    parsed = urlparse(db_url)
    hostname = parsed.hostname
    port = parsed.port or 5432

    if not hostname:
        _print_result("DATABASE_URL", False, "configured URL is missing a hostname")
        return False

    _print_result("DATABASE_URL", True, f"configured for host {hostname}:{port}")
    dns_ok = _check_dns(hostname)
    tcp_ok = _check_tcp(hostname, port) if dns_ok else False
    return dns_ok and tcp_ok


def main() -> int:
    results = [
        _check_toggl_token(),
        _check_supabase_http_env(),
        _check_database_url(),
    ]
    if all(results):
        print("Environment readiness check passed")
        return 0
    print("Environment readiness check failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
