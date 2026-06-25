"""Gunicorn config. Reads the port from $PORT at runtime so the start command
never contains a literal "$PORT" (Railway runs custom start commands without a
shell, which left "$PORT" unexpanded and crashed the app)."""
import os

bind = "0.0.0.0:" + os.environ.get("PORT", "8080")
workers = 1
threads = 8
timeout = 300
