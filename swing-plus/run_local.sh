#!/bin/bash
# Starts the Swing+/Hitter+ tool locally on http://localhost:8000
cd "$(dirname "$0")"
exec .venv/bin/python -m uvicorn web.app:app --host 127.0.0.1 --port 8000 --log-level warning
