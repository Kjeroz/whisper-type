# Whisper Type

Offline voice dictation for Linux. Speak, and text appears at your cursor.

- **Fully offline** — no API keys, no data leaves your machine
- **System tray icon** — red dot when recording, microphone when idle
- **Two-pass transcription** — English first for commands, then your selected language for sentences
- **Keyboard shortcut** — configurable hotkey to start/stop recording
- **Push-to-talk** — hold keys to record, release to transcribe
- **Voice language switch** — say a language name in English to switch
- **99+ languages** via OpenAI Whisper

## Quick Start

### Prerequisites

- **Linux** with X11 desktop (Cinnamon, GNOME, KDE, XFCE)
- **Python 3.11+**
- **Microphone** (USB, built-in, or Bluetooth)
- **xdotool** (for text input)

#### Install system dependencies

**Ubuntu / Debian:**
```bash
sudo apt install python3 python3-venv python3-dev \
    portaudio19-dev python3-gi gir1.2-ayatanaappindicator3-0.1 \
    xdotool git
```

**Fedora:**
```bash
sudo dnf install python3 portaudio-devel python3-gobject \
    libappindicator-gtk3 xdotool git
```

**Arch:**
```bash
sudo pacman -S portaudio python-gobject libappindicator-gtk3 xdotool git
```

### Install

```bash
git clone https://github.com/Kjeroz/whisper-type.git
cd whisper-type
chmod +x install.sh
./install.sh
```

The installer will:
1. Check for Python 3.11+
2. Install missing system packages (prompts for sudo password)
3. Create a virtual environment
4. Install Python dependencies (Whisper, PyAudio, pynput, etc.)
5. Verify everything works
6. Set up autostart on login

### Run

```bash
./run.sh
```

A microphone icon appears in your system tray. Left-click it for settings.

The first run downloads the Whisper model (~74 MB for base). Subsequent starts are instant.

## Usage

### Recording

Hold your configured hotkey (default: **Ctrl+Shift**) to record, release to transcribe. This is push-to-talk mode.

Or use toggle mode: press the hotkey once to start, once to stop.

Toggle between modes: tray icon > Settings > Push-to-Talk.

### System Tray

Left-click the microphone icon:

- **Start / Stop Recording**
- **Settings**
  - **Model** — tiny, base, small, medium, large
  - **Language** — English (default), French, Swedish, Auto-detect, etc.
  - **Audio Device** — pick your microphone
  - **Max Time** — 10s, 30s, 60s, 120s recording limit
  - **Push-to-Talk** — toggle hold-to-record mode
  - **Key Binding** — click then press new key combo
  - **Edit Config File** — open config in text editor
- **Quit**

### How Transcription Works

Whisper Type uses a **two-pass system**:

1. **Pass 1 (English)** — always runs first. Detects word count and checks for language commands.
2. **Pass 2 (selected language)** — only runs for multi-word sentences. Re-transcribes in your chosen language.

| What you say | Pass 1 result | What happens |
|-------------|---------------|--------------|
| "french" | 1 word, matches language | Switches to French, nothing typed |
| "hello" | 1 word, not a language | Types "hello" |
| "comment allez-vous" | Multi-word | Pass 2 in French, types transcription |
| "auto" | 1 word, matches language | Switches to auto-detect mode |

### Voice Language Commands

Say a language name **in English, by itself** to switch. The first pass always listens in English, so only English names work.

| Say | What happens |
|-----|-------------|
| "French" | Switches to French |
| "German" | Switches to German |
| "Swedish" | Switches to Swedish |
| "English" | Switches to English |
| "Auto" | Switches to auto-detect mode |

Works only for English names — "Francais", "Deutsch", "Svenska" are **not** recognized. Use the English word.

### Choosing a Model

| Model | Size | RAM Needed | Best For |
|-------|------|-----------|----------|
| tiny | 39 MB | ~1 GB | Quick dictation, low resources |
| base | 74 MB | ~1 GB | Everyday use (recommended) |
| small | 244 MB | ~2 GB | Better accuracy |
| medium | 769 MB | ~5 GB | High accuracy |
| large | 1550 MB | ~10 GB | Best accuracy, slow |

Start with **base**. Upgrade to **small** if you need better accuracy. The model downloads automatically on first use.

## Command-Line Options

```bash
./run.sh [OPTIONS]
```

```
-m MODEL       tiny, base, small, medium, large (default: base)
-d DEVICE      Audio device index (default: auto-detect)
-l LANG        Language code: en, fr, es, de, etc. (default: en)
-t SECONDS     Max recording time (default: 60)
-k KEYS        Keyboard shortcut (default: ctrl+shift)
--push-to-talk Hold keys to record instead of toggle
--list-devices Show available microphones
```

### Find your microphone

```bash
./run.sh --list-devices
# Example output:
#   0: Built-in Audio Analog Stereo
#   4: USB Microphone
#
# Then select device 4 in tray icon > Settings > Audio Device
```

## Configuration

Settings are saved to `~/.config/whisper-dictation/config.json`:

```json
{
  "model": "base",
  "device": 4,
  "max_time": 60,
  "language": "en",
  "push_to_talk": true,
  "key_combination": "ctrl+shift"
}
```

- `language: "en"` is the default (English). Set to `null` for auto-detect.
- Edit via tray icon > Settings > Edit Config File, or manually.

### Recording Icon

When recording, the tray icon changes to a **red dot** and shows "Recording" in the tooltip. The icon stays in the same position in the panel (no shifting).

A red dot PNG is generated automatically on first run at `~/.local/share/whisper-dictation/icons/recording.png`.

## Autostart

The installer sets up autostart so Whisper Type launches on login. The autostart entry is at:

```
~/.config/autostart/whisper-dictation.desktop
```

To disable autostart: remove that file or uncheck it in your desktop's startup settings.

## Troubleshooting

**No tray icon appears:**
- Make sure you're on X11, not Wayland. Check with: `echo $XDG_SESSION_TYPE`
- If it says "wayland", switch to X11 at the login screen (gear icon)

**"Invalid sample rate" error:**
- Your audio device may not support 16kHz. Run `./run.sh --list-devices` and select a different device in Settings.

**Keyboard shortcut doesn't work:**
```bash
sudo usermod -a -G input $USER
# Log out and back in
```

**Model fails to load (out of memory):**
- The error dialog shows VRAM/RAM requirements. Try a smaller model (tiny or base).

**ALSA warnings in terminal:**
- Harmless. They appear because of multiple audio devices. The app still works.

**Text doesn't appear after recording:**
- Make sure `xdotool` is installed: `which xdotool`
- Install if missing: `sudo apt install xdotool` (Ubuntu/Debian)

**Transcription is gibberish:**
- You probably spoke in a different language than what was selected. Say "auto" to switch to auto-detect mode, or say the correct language name.

**Voice language switch not working:**
- Language names must be spoken **in English** ("French", not "Francais")
- Must be a single word by itself ("French" yes, "French please" no)

## Uninstall

```bash
rm -rf ~/whisper-dictation
rm ~/.config/autostart/whisper-dictation.desktop
rm -rf ~/.config/whisper-dictation
rm -rf ~/.local/share/whisper-dictation
```

## License

MIT License - see [LICENSE](LICENSE)
