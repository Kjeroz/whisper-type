#!/bin/bash
# Whisper Dictation launcher
# Usage: ./run.sh [options]
# Run with --help for all options

cd "$(dirname "$0")"
exec ./venv/bin/python whisper-dictation-linux.py "$@" 2>/dev/null
