#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import ipaddress
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def configure_lan_runserver():
    if len(sys.argv) < 2 or sys.argv[1] != "runserver":
        return
    if any(not arg.startswith("-") for arg in sys.argv[2:]):
        return

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
    if os.environ.get("DJANGO_DEBUG", "False").strip().lower() not in {"1", "true", "yes", "on"}:
        return

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            route.connect(("192.0.2.1", 80))
            lan_ip = route.getsockname()[0]
    except OSError:
        return

    current_url = os.environ.get("SITE_URL", "http://127.0.0.1:8000").rstrip("/")
    parsed_url = urlsplit(current_url)
    hostname = parsed_url.hostname or ""
    try:
        is_local_site = hostname == "localhost" or ipaddress.ip_address(hostname).is_private
    except ValueError:
        is_local_site = False
    if is_local_site:
        netloc = f"{lan_ip}:{parsed_url.port or 8000}"
        os.environ["SITE_URL"] = urlunsplit((parsed_url.scheme or "http", netloc, "", "", ""))

    sys.argv.insert(2, "0.0.0.0:8000")
    site_url = os.environ.get("SITE_URL", f"http://{lan_ip}:8000").rstrip("/")
    print(f"Laptop URL: http://127.0.0.1:8000/")
    print(f"Phone URL (same Wi-Fi): {site_url}/")
    print("Use the URLs above; 0.0.0.0 is the server bind address, not a browser link.")


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'routelync.settings')
    configure_lan_runserver()
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
