#!/bin/bash
# ReliefKit installer (macOS). Idempotent.
set -e
cd "$(dirname "$0")"

if ! command -v brew >/dev/null; then
  echo "Homebrew is required: https://brew.sh"; exit 1
fi

echo "== brew packages =="
brew list gdal >/dev/null 2>&1 || brew install gdal
brew list python@3.12 >/dev/null 2>&1 || brew install python@3.12
if ! command -v blender >/dev/null && [ ! -d "/Applications/Blender.app" ]; then
  brew install --cask blender
fi

echo "== done =="  # server is stdlib-only, no pip packages needed
echo "Run:  ./run.sh    then open http://localhost:8765"
