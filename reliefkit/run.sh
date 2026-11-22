#!/bin/bash
cd "$(dirname "$0")"
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
exec "$PY" server.py "$@"
