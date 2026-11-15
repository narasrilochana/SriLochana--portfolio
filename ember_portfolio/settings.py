"""Loads secrets from a private .env file into environment variables.

No extra library needed. Real environment variables always win, so on Render
you simply set them in the dashboard and no file is required.

Search order: $ENV_FILE, then ./.env next to main.py, then ~/.portfolio.env
The file holds lines like  KEY=value  and must NEVER be committed to GitHub.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def load_env() -> None:
    candidates = [os.environ.get("ENV_FILE", ""), BASE_DIR / ".env", Path.home() / ".portfolio.env"]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return


load_env()
