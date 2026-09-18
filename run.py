"""Локальный запуск: .venv/bin/python run.py."""

import os

from dotenv import load_dotenv

from campus import ROOT, create_app

if __name__ == "__main__":
    load_dotenv(ROOT / ".env")
    port = int(os.environ.get("APP_PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("APP_PORT должен быть от 1 до 65535")
    create_app().run(host=os.environ.get("APP_HOST", "127.0.0.1"), port=port, debug=False)
