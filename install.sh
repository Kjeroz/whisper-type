#!/bin/bash
# Whisper Dictation - Linux Installer
# Installs whisper-dictation with system tray icon on Linux (X11 + Cinnamon/GNOME/KDE)
set -e

INSTALL_DIR="${WHISPER_DICTATION_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
PYTHON_REQ="3.12"

echo "╔══════════════════════════════════════════╗"
echo "║   Whisper Dictation - Linux Installer    ║"
echo "╚══════════════════════════════════════════╝"
echo ""

echo "  Installation directory: $INSTALL_DIR"
# ── Check Python ──────────────────────────────────────
echo "[1/6] Checking Python..."
if command -v python3.12 &>/dev/null; then
    PYTHON=python3.12
elif command -v python3.11 &>/dev/null; then
    PYTHON=python3.11
elif command -v python3 &>/dev/null; then
    PYTHON=python3
else
    echo "ERROR: Python 3.11+ not found. Install with:"
    echo "  sudo apt install python3.12 python3.12-venv python3.12-dev"
    exit 1
fi

PY_VERSION=$($PYTHON --version 2>&1 | grep -oP '\d+\.\d+')
echo "  Found: $($PYTHON --version) at $(which $PYTHON)"

# ── Check system dependencies ─────────────────────────
echo "[2/6] Checking system dependencies..."
MISSING=""
for pkg in portaudio19-dev python3-gi gir1.2-ayatanaappindicator3-0.1; do
    if ! dpkg -s "$pkg" &>/dev/null 2>&1; then
        MISSING="$MISSING $pkg"
    fi
done

if [ -n "$MISSING" ]; then
    echo "  Installing missing system packages:$MISSING"
    sudo apt update -qq
    sudo apt install -y -qq$MISSING
else
    echo "  All system packages installed"
fi

# ── Create venv ───────────────────────────────────────
echo "[3/6] Setting up virtual environment..."
if [ ! -d "$INSTALL_DIR/venv" ]; then
    echo "  Creating venv with --system-site-packages (for GTK/GI)..."
    $PYTHON -m venv "$INSTALL_DIR/venv" --system-site-packages
else
    echo "  venv already exists"
fi

# ── Install Python dependencies ───────────────────────
echo "[4/6] Installing Python packages..."
echo "  Note: Installing CPU-only version of Torch to save ~2GB of disk space"
echo "  (No NVIDIA GPU detected)"

# Upgrade pip and install CPU torch
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip --no-cache-dir
"$INSTALL_DIR/venv/bin/pip" install torch --index-url https://download.pytorch.org/whl/cpu --no-cache-dir

# Install the rest
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --no-cache-dir
echo "  Done"

# ── Verify installation ───────────────────────────────
echo "[5/6] Verifying installation..."
"$INSTALL_DIR/venv/bin/python" -c "
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import Gtk, AyatanaAppIndicator3
import pyaudio, numpy, whisper
print('  All checks passed')
" 2>/dev/null || {
    echo "  WARNING: Some components failed verification"
    echo "  The app may still work, but check the error above"
}

# ── Desktop entry (autostart) ─────────────────────────
echo "[6/6] Setting up autostart..."
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/whisper-dictation.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Whisper Dictation
Exec=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/whisper-dictation-linux.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Comment=Offline voice dictation using OpenAI Whisper
EOF
echo "  Autostart entry created at $AUTOSTART_DIR/whisper-dictation.desktop"

# ── Create launcher ───────────────────────────────────
chmod +x "$INSTALL_DIR/run.sh" 2>/dev/null || true

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║           Installation Complete!          ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Quick start:"
echo "  cd $INSTALL_DIR"
echo "  ./venv/bin/python whisper-dictation-linux.py"
echo ""
echo "Or use the launcher:"
echo "  $INSTALL_DIR/run.sh"
echo ""
echo "List audio devices:"
echo "  $INSTALL_DIR/venv/bin/python whisper-dictation-linux.py --list-devices"
echo ""
echo "Keyboard shortcut: Ctrl+Shift (toggle) or Ctrl+Shift (push-to-talk)"
echo "System tray icon: Left-click for settings, model, language, device"
echo ""
echo "To uninstall:"
echo "  rm -rf $INSTALL_DIR"
echo "  rm $HOME/.config/autostart/whisper-dictation.desktop"
