# Whisper Dictation

Offline voice dictation for Linux using OpenAI Whisper. Speak, and text appears at your cursor.

- **Fully offline** - no API keys, no data leaves your machine
- **System tray icon** - left-click for settings (model, language, device, timing)
- **Keyboard shortcut** - Ctrl+Alt to toggle recording (configurable)
- **Push-to-talk** - hold keys to record, release to transcribe
- **Multilingual** - supports 99+ languages via Whisper

## Install

```bash
git clone https://github.com/USER/whisper-dictation.git
cd whisper-dictation
chmod +x install.sh
./install.sh
```

The installer:
1. Installs system dependencies (portaudio, GTK, AppIndicator)
2. Creates a Python 3.12 venv with `--system-site-packages`
3. Installs all Python packages
4. Sets up autostart on login

## Usage

```bash
# Start the app
./run.sh

# Or directly
./venv/bin/python whisper-dictation-linux.py

# List audio devices
./venv/bin/python whisper-dictation-linux.py --list-devices
```

### System Tray

Left-click the tray icon to access:
- **Start/Stop Recording**
- **Settings** > Model, Language, Audio Device, Max Time, Push-to-Talk
- **Quit**

### Keyboard Shortcuts

| Mode | Action |
|------|--------|
| **Toggle** (default) | Press Ctrl+Alt to start, press again to stop |
| **Push-to-Talk** | Hold Ctrl+Alt to record, release to transcribe |

Change shortcut: `-k alt+shift`

### Command-Line Options

```
-m MODEL       Whisper model: tiny, base, small, medium, large (default: base)
-d DEVICE      Audio device index (default: auto-detect)
-l LANG        Language code: en, fr, es, de, etc. (default: auto-detect)
-t SECONDS     Max recording time (default: 60)
-k KEYS        Keyboard shortcut (default: ctrl+alt)
--push-to-talk Hold keys to record instead of toggle
--list-devices Show available microphones
```

### Models

| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| tiny | 39 MB | Fast | Basic |
| base | 74 MB | Good | Good |
| small | 244 MB | Medium | Better |
| medium | 769 MB | Slow | Great |
| large | 1550 MB | Very slow | Best |

First run downloads the model (~74 MB for base).

## Configuration

Settings are saved to `~/.config/whisper-dictation/config.json`:

```json
{
  "model": "base",
  "device": 4,
  "max_time": 60,
  "language": "en",
  "push_to_talk": false,
  "key_combination": "ctrl+alt"
}
```

Edit via tray icon > Settings > Edit Config File, or manually.

## System Requirements

- **OS**: Linux (Ubuntu/Debian, Fedora, Arch)
- **Desktop**: X11 (Cinnamon, GNOME, KDE, XFCE)
- **Python**: 3.11+
- **RAM**: ~1 GB (base model), ~4 GB (medium)
- **Microphone**: Any (USB, built-in, Bluetooth)

### Required System Packages

```bash
# Ubuntu/Debian
sudo apt install python3.12 python3.12-venv python3.12-dev \
    portaudio19-dev python3-gi gir1.2-ayatanaappindicator3-0.1

# Fedora
sudo dnf install python3 portaudio-devel python3-gobject \
    libappindicator-gtk3

# Arch
sudo pacman -S portaudio python-gobject libappindicator-gtk3
```

## Troubleshooting

**No tray icon**: Ensure you're on X11, not Wayland. Check `echo $XDG_SESSION_TYPE`.

**"Invalid sample rate" error**: Your audio device may not support 16kHz. Try a different device with `--list-devices`.

**Keyboard shortcut doesn't work**: Add your user to the `input` group:
```bash
sudo usermod -a -G input $USER
# Log out and back in
```

**ALSA warnings**: Harmless. Can be suppressed by setting `--list-devices` to find your device.

## Uninstall

```bash
rm -rf ~/whisper-dictation
rm ~/.config/autostart/whisper-dictation.desktop
rm -rf ~/.config/whisper-dictation
```

## License

MIT License - see [LICENSE](LICENSE)
