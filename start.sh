#!/bin/bash
# Start whisper-dictation in background
cd "$(dirname "$0")"
nohup ./venv/bin/python whisper-dictation-linux.py > /dev/null 2>&1 &
echo "Whisper Dictation started (PID $!)"
