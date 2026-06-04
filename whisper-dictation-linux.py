import os
import sys
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import Gtk, AyatanaAppIndicator3, GLib

import argparse
import time
import threading
import pyaudio
import numpy as np
from pynput import keyboard
import subprocess
from whisper import load_model

# ── Config ──────────────────────────────────────────────
try:
    from config import get_config, update_config
    CONFIG_OK = True
except ImportError:
    CONFIG_OK = False

_AUTO = "__auto__"  # sentinel for auto-detect language

# Constant title — kept the same in both states so the panel slot doesn't
# resize and shift the icon position when toggling recording.
_TRAY_TITLE = "Whisper Dictation"
_IDLE_ICON = "audio-input-microphone"
_REC_ICON_NAME = "media-record"  # fallback theme icon (used if cairo missing)


def _ensure_recording_icon():
    """Generate a 22x22 red-dot PNG in XDG_DATA_HOME on first run.

    Returns the absolute path. The icon name never changes between states
    (we keep `_IDLE_ICON` for idle, the file path for recording), so the
    AppIndicator slot doesn't shift and we avoid "broken icon" lookups for
    theme names that may not exist on every desktop.
    """
    icon_dir = Path(os.environ.get("XDG_DATA_HOME",
                                   Path.home() / ".local" / "share")) \
        / "whisper-dictation" / "icons"
    icon_dir.mkdir(parents=True, exist_ok=True)
    rec_path = icon_dir / "recording.png"
    if rec_path.exists():
        return str(rec_path)
    try:
        import cairo
        size = 22
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        ctx = cairo.Context(surface)
        ctx.set_source_rgba(0, 0, 0, 0)
        ctx.paint()
        ctx.set_source_rgba(0.85, 0.1, 0.1, 1.0)
        ctx.arc(size / 2, size / 2, size / 2 - 2, 0, 2 * 3.14159)
        ctx.fill()
        ctx.set_source_rgba(1, 1, 1, 0.25)
        ctx.arc(size / 2 - 2, size / 2 - 2, 2.5, 0, 2 * 3.14159)
        ctx.fill()
        surface.write_to_png(str(rec_path))
        return str(rec_path)
    except Exception:
        return None  # caller falls back to _REC_ICON_NAME

COMMON_LANGS = [None, 'en', 'fr', 'es', 'de', 'it', 'pt', 'nl', 'ru', 'zh', 'ja', 'ko', 'ar', 'sv', 'no', 'da', 'fi', 'pl', 'tr', 'hi', 'th', 'vi']

_LANG_NAMES = {
    None: 'Auto-detect',
    'en': 'English', 'fr': 'French', 'es': 'Spanish', 'de': 'German',
    'it': 'Italian', 'pt': 'Portuguese', 'nl': 'Dutch', 'ru': 'Russian',
    'zh': 'Chinese', 'ja': 'Japanese', 'ko': 'Korean', 'ar': 'Arabic',
    'sv': 'Swedish', 'no': 'Norwegian', 'da': 'Danish', 'fi': 'Finnish',
    'pl': 'Polish', 'tr': 'Turkish', 'hi': 'Hindi', 'th': 'Thai', 'vi': 'Vietnamese',
}

# English-only single-word voice commands. Anything not in this dict triggers
# an "unrecognized language" popup. The point of the constraint: a stray
# "green" in a non-English-configured session used to come back as a Chinese
# homophone, which then matched the previous multi-language dict and silently
# switched the active language.
_VOICE_LANG_ENGLISH = {
    'english': 'en', 'french': 'fr', 'spanish': 'es', 'german': 'de',
    'italian': 'it', 'portuguese': 'pt', 'dutch': 'nl', 'russian': 'ru',
    'chinese': 'zh', 'japanese': 'ja', 'korean': 'ko', 'arabic': 'ar',
    'swedish': 'sv', 'norwegian': 'no', 'danish': 'da', 'finnish': 'fi',
    'polish': 'pl', 'turkish': 'tr', 'hindi': 'hi', 'thai': 'th',
    'vietnamese': 'vi',
    'auto': _AUTO, 'automatic': _AUTO, 'detect': _AUTO, 'autodetect': _AUTO,
}

# ── SpeechTranscriber ───────────────────────────────────
_HALLUCINATIONS = {
    'thanks for watching', 'thank you for watching', 'thank you for watching!',
    'thanks for watching!', 'subscribe', 'subscribe!', 'please subscribe',
    'please subscribe!', 'thanks for watching. bye', 'see you next time',
    'see you in the next video', 'bye', 'bye!', 'bye bye',
    'you', 'the', 'a', 'i', 'oh', 'um', 'uh',
}

class SpeechTranscriber:
    def __init__(self, model, on_language_switch=None):
        self.model = model
        self.kb = keyboard.Controller()
        self.on_language_switch = on_language_switch
        self.use_clipboard = True  # clipboard paste is more reliable than pynput typing

    def _paste_via_clipboard(self, text):
        """Type text via xdotool (direct text injection, no Ctrl+V needed)"""
        try:
            subprocess.run(['xdotool', 'type', '--clearmodifiers', text],
                           check=True)
        except Exception as e:
            print(f"xdotool type failed, falling back to typing: {e}", flush=True)
            self._type_via_keyboard(text)

    def _type_via_keyboard(self, text):
        """Fallback: type character by character via pynput"""
        for ch in text:
            try:
                self.kb.type(ch)
                time.sleep(0.0025)
            except Exception:
                pass

    def _emit(self, text):
        """Route text to active paste method."""
        if self.use_clipboard:
            self._paste_via_clipboard(text)
        else:
            self._type_via_keyboard(text)

    def _validate(self, result):
        """Common post-transcription checks. Returns clean text or None to skip."""
        segments = result.get("segments", [])
        if segments:
            avg_nsp = sum(s.get("no_speech_prob", 0) for s in segments) / len(segments)
            if avg_nsp > 0.5:
                print(f"Skipped (no_speech_prob={avg_nsp:.2f})", flush=True)
                return None
        text = result["text"].strip()
        if not text:
            return None
        if text.lower().strip('!.,;:?!') in _HALLUCINATIONS:
            print(f"Skipped hallucination: {text}", flush=True)
            return None
        return text

    def transcribe(self, audio_data, language=None):
        """Two-pass transcription.

        Pass 1 — English: determines whether this is a single-word language
        command, a single word to type directly, or a multi-word sentence.
        Pass 2 — selected language: only for multi-word sentences, re-transcribes
        using the user's chosen language so the output matches the target.
        """
        # ── Pass 1: always English ──────────────────────────────────
        text1 = self._validate(self.model.transcribe(audio_data, language='en'))
        if text1 is None:
            return

        words = text1.split()

        # Single word → language command or type it
        if len(words) == 1:
            w = words[0].lower().strip('!.,;:?!')
            if w in _VOICE_LANG_ENGLISH and self.on_language_switch:
                print(f"Voice switch: {w} → {_VOICE_LANG_ENGLISH[w]}", flush=True)
                self.on_language_switch(_VOICE_LANG_ENGLISH[w])
                return
            # Not a language name → type the single word
            self._emit(text1)
            return

        # ── Pass 2: selected language ───────────────────────────────
        # Multi-word: re-transcribe in the user's chosen language.
        # `language` is the config value (e.g. 'fr', 'de', None for auto-detect).
        text2 = self._validate(self.model.transcribe(audio_data, language=language))
        if text2 is None:
            return
        self._emit(text2)

# ── Recorder ───────────────────────────────────────────
class Recorder:
    def __init__(self, transcriber, device_index=None):
        self.recording = False
        self.transcriber = transcriber
        self.device_index = device_index

    def start(self, language=None):
        threading.Thread(target=self._record_impl, args=(language,), daemon=True).start()

    def stop(self):
        self.recording = False

    def _record_impl(self, language):
        self.recording = True
        FRAMES = 1024
        p = pyaudio.PyAudio()
        try:
            try:
                stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                                frames_per_buffer=FRAMES, input=True,
                                input_device_index=self.device_index)
            except Exception as e:
                print(f"Audio device error: {e}")
                stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                                frames_per_buffer=FRAMES, input=True)
            frames = []
            try:
                while self.recording:
                    frames.append(stream.read(FRAMES, exception_on_overflow=False))
            finally:
                stream.stop_stream()
                stream.close()
        finally:
            p.terminate()
        audio = np.frombuffer(b''.join(frames), dtype=np.int16).astype(np.float32) / 32768.0
        if len(audio) < 8000:  # <0.5s at 16kHz
            print("Skipped (too short)", flush=True)
            return
        self.transcriber.transcribe(audio, language)

# ── GlobalKeyListener ─────────────────────────────────────
class GlobalKeyListener:
    def __init__(self, app, key_combo, push_to_talk=False):
        self.app = app
        parts = key_combo.split('+')
        self.k1 = parts[0]
        self.k2 = parts[1] if len(parts) > 1 else None
        self.k1_down = False
        self.k2_down = False
        self.ptt = push_to_talk

    def _matches(self, key, target):
        if hasattr(key, 'name') and key.name == target:
            return True
        if hasattr(key, 'char') and key.char == target:
            return True
        return False

    def on_press(self, key):
        if self._matches(key, self.k1): self.k1_down = True
        if self.k2 and self._matches(key, self.k2): self.k2_down = True
        combo = self.k1_down and (self.k2 is None or self.k2_down)
        if combo:
            if self.ptt and not self.app.started:
                GLib.idle_add(self.app.start_app)
            elif not self.ptt:
                GLib.idle_add(self.app.toggle)

    def on_release(self, key):
        if self._matches(key, self.k1): self.k1_down = False
        if self.k2 and self._matches(key, self.k2): self.k2_down = False
        if self.ptt and self.app.started:
            if self.k2 is None:
                if not self.k1_down:
                    GLib.idle_add(self.app.stop_app)
            elif not self.k1_down or not self.k2_down:
                GLib.idle_add(self.app.stop_app)

# ── GTK TrayApp ─────────────────────────────────────────
class TrayApp:
    def __init__(self, recorder, languages=None, max_time=60, ptt=False, models=None):
        self.recorder = recorder
        self.languages = languages
        if isinstance(languages, str):
            self.current_lang = languages
        else:
            self.current_lang = (languages[0] if languages else None)
        self.started = False
        self.max_time = max_time
        self.ptt = ptt
        self.models = models or ['tiny', 'base', 'small', 'medium', 'large']
        self.current_model = 'base'
        self.timer = None
        self.keylistener = None
        self.current_key = None
        self.config = None
        self.indicator = None
        self._build_indicator()

    def _build_indicator(self):
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            "whisper-dictation",
            _IDLE_ICON,
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
        # Resolve the recording icon once; fall back to a theme name if cairo
        # failed. Either way, the icon *name* will change (icon name string
        # versus file path), but the title text stays constant so the panel
        # slot doesn't resize.
        self._recording_icon = _ensure_recording_icon() or _REC_ICON_NAME
        self.indicator.set_title(_TRAY_TITLE)
        self._update_icon()
        self.indicator.set_menu(self._build_menu())

    def _update_icon(self):
        if self.started:
            self.indicator.set_icon_full(self._recording_icon, "Recording — click to stop")
        else:
            self.indicator.set_icon_full(_IDLE_ICON, "Idle — click for menu")

    def _build_menu(self):
        menu = Gtk.Menu()

        # Start Recording
        self.item_start = Gtk.MenuItem(label="Start Recording")
        self.item_start.connect("activate", lambda _: self.start_app())
        self.item_start.set_sensitive(not self.started)
        menu.append(self.item_start)

        # Stop Recording
        self.item_stop = Gtk.MenuItem(label="Stop Recording")
        self.item_stop.connect("activate", lambda _: self.stop_app())
        self.item_stop.set_sensitive(self.started)
        menu.append(self.item_stop)

        # Separator
        menu.append(Gtk.SeparatorMenuItem())

        # Settings submenu
        settings_item = Gtk.MenuItem(label="Settings")
        settings_menu = Gtk.Menu()

        # Model submenu
        model_menu = Gtk.Menu()
        self.model_radio_items = []
        for m in self.models:
            item = Gtk.RadioMenuItem(label=m)
            item._model = m
            if self.model_radio_items:
                item.join_group(self.model_radio_items[0])
            item.set_active(m == self.current_model)
            item.connect("toggled", lambda w, m=m: self._set_model(m))
            model_menu.append(item)
            self.model_radio_items.append(item)
        model_item = Gtk.MenuItem(label="Model")
        model_item.set_submenu(model_menu)
        settings_menu.append(model_item)

        # Max Time submenu
        time_menu = Gtk.Menu()
        self.time_radio_items = []
        for t in [10, 30, 60, 120]:
            item = Gtk.RadioMenuItem(label=f"{t}s")
            item._time = t
            if self.time_radio_items:
                item.join_group(self.time_radio_items[0])
            item.set_active(t == self.max_time)
            item.connect("toggled", lambda w, t=t: self._set_time(t))
            time_menu.append(item)
            self.time_radio_items.append(item)
        time_item = Gtk.MenuItem(label="Max Time")
        time_item.set_submenu(time_menu)
        settings_menu.append(time_item)

        # Audio Device submenu
        device_menu = Gtk.Menu()
        self.device_radio_items = []
        try:
            p = pyaudio.PyAudio()
            cur = self.recorder.device_index if self.recorder.device_index is not None else -1
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    item = Gtk.RadioMenuItem(label=f"{i}: {info['name']}")
                    item._device = i
                    if self.device_radio_items:
                        item.join_group(self.device_radio_items[0])
                    item.set_active(i == cur)
                    item.connect("toggled", lambda w, d=i: self._set_device(d))
                    device_menu.append(item)
                    self.device_radio_items.append(item)
            p.terminate()
        except Exception as e:
            print(f"Audio device enumeration failed: {e}", flush=True)
        device_item = Gtk.MenuItem(label="Audio Device")
        device_item.set_submenu(device_menu)
        settings_menu.append(device_item)

        # Language submenu
        lang_menu = Gtk.Menu()
        self.lang_radio_items = []
        cur_lang = self.current_lang
        for l in COMMON_LANGS:
            item = Gtk.RadioMenuItem(label=_LANG_NAMES.get(l, l))
            item._lang = l
            if self.lang_radio_items:
                item.join_group(self.lang_radio_items[0])
            item.set_active(l == cur_lang)
            item.connect("toggled", lambda w, l=l: self._set_lang(l))
            lang_menu.append(item)
            self.lang_radio_items.append(item)
        lang_item = Gtk.MenuItem(label="Language")
        lang_item.set_submenu(lang_menu)
        settings_menu.append(lang_item)

        # Push-to-Talk toggle
        ptt_item = Gtk.CheckMenuItem(label="Push-to-Talk")
        ptt_item.set_active(self.ptt)
        ptt_item.connect("toggled", lambda w: self._toggle_ptt())
        settings_menu.append(ptt_item)
        self.ptt_item = ptt_item

        # Key Binding
        self.current_key = None  # set after build
        kb_item = Gtk.MenuItem(label="Key Binding")
        kb_item.connect("activate", lambda _: self._set_keybinding())
        settings_menu.append(kb_item)

        # Separator
        settings_menu.append(Gtk.SeparatorMenuItem())

        # Edit Config
        edit_item = Gtk.MenuItem(label="Edit Config File")
        edit_item.connect("activate", lambda _: self._edit_config())
        settings_menu.append(edit_item)

        settings_item.set_submenu(settings_menu)
        menu.append(settings_item)

        # Separator
        menu.append(Gtk.SeparatorMenuItem())

        # Quit
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda _: self.quit_app())
        menu.append(quit_item)

        menu.show_all()
        return menu

    def _set_model(self, m):
        prev = self.current_model
        self.current_model = m
        if CONFIG_OK: update_config(model=m)
        def _load():
            print(f"Loading model: {m}", flush=True)
            try:
                new_model = load_model(m)
                self.recorder.transcriber.model = new_model
                print(f"Model {m} loaded", flush=True)
            except Exception as e:
                print(f"Model error: {e}", flush=True)
                self.current_model = prev
                if CONFIG_OK: update_config(model=prev)
                def revert_and_show():
                    for item in self.model_radio_items:
                        if item._model == prev:
                            item.set_active(True)
                            break
                    self._show_error(f"Failed to load '{m}' model.", self._model_error_hint(m, e))
                GLib.idle_add(revert_and_show)
        threading.Thread(target=_load, daemon=True).start()

    def _set_time(self, t):
        self.max_time = t
        print(f"Max time: {t}s", flush=True)
        if CONFIG_OK: update_config(max_time=t)

    def _set_device(self, d):
        self.recorder.device_index = d
        print(f"Device: {d}", flush=True)
        if CONFIG_OK: update_config(device=d)

    def _set_lang(self, l):
        self.current_lang = None if l == _AUTO else l
        print(f"Language: {self.current_lang or 'auto-detect'}", flush=True)
        if CONFIG_OK: update_config(language=self.current_lang)

    def _switch_lang(self, l):
        """Called from voice command — updates config + radio buttons."""
        self.current_lang = None if l == _AUTO else l
        if CONFIG_OK: update_config(language=self.current_lang)
        def _update_ui():
            for item in self.lang_radio_items:
                if item._lang == self.current_lang:
                    item.set_active(True)
                    break
        GLib.idle_add(_update_ui)
        print(f"Voice switch language: {self.current_lang or 'auto-detect'}", flush=True)

    def _toggle_ptt(self):
        self.ptt = self.ptt_item.get_active()
        print(f"Push-to-talk: {self.ptt}", flush=True)
        if self.keylistener:
            self.keylistener.ptt = self.ptt
        if CONFIG_OK: update_config(push_to_talk=self.ptt)
        self._update_icon()

    def _set_keybinding(self):
        current = self.current_key or "not set"
        dialog = Gtk.MessageDialog(
            transient_for=None,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.NONE,
            text=f"Current shortcut: {current}",
        )
        dialog.format_secondary_text("Hold new keys, then release to confirm.\nPress Escape to cancel.")
        keys_held = []
        captured = [False]

        def on_press(key):
            if captured[0]: return False
            if key == keyboard.Key.esc:
                GLib.idle_add(dialog.response, Gtk.ResponseType.CANCEL)
                return False
            if key not in keys_held:
                keys_held.append(key)
            names = [getattr(k, 'name', None) or getattr(k, 'char', None) or str(k) for k in keys_held]
            GLib.idle_add(lambda n='+'.join(names): dialog.format_secondary_text(f"Keys: {n}\nRelease to confirm."))
            return True

        def on_release(key):
            if captured[0]: return False
            if len(keys_held) == 0: return True
            names = [getattr(k, 'name', None) or getattr(k, 'char', None) or str(k) for k in keys_held]
            combo_str = '+'.join(names)
            captured[0] = True
            GLib.idle_add(lambda c=combo_str: self._apply_keybinding(c, dialog))
            return False

        keyboard.Listener(on_press=on_press, on_release=on_release).start()
        dialog.run()
        dialog.destroy()

    def _apply_keybinding(self, combo_str, dialog):
        dialog.response(Gtk.ResponseType.OK)
        self.current_key = combo_str
        if CONFIG_OK: update_config(key_combination=combo_str)
        self.keylistener = GlobalKeyListener(self, combo_str, push_to_talk=self.ptt)
        keyboard.Listener(on_press=self.keylistener.on_press,
                         on_release=self.keylistener.on_release).start()
        print(f"Key binding: {combo_str}", flush=True)

    def _show_error(self, title, detail):
        dialog = Gtk.MessageDialog(
            transient_for=None,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=title,
        )
        dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()

    _MODEL_HELP = {
        "tiny":  "tiny:  ~1 GB VRAM /  ~1 GB RAM",
        "base":  "base:  ~1 GB VRAM /  ~1 GB RAM",
        "small": "small: ~2 GB VRAM /  ~2 GB RAM",
        "medium": "medium: ~5 GB VRAM /  ~5 GB RAM",
        "large": "large: ~10 GB VRAM / ~10 GB RAM",
    }

    def _model_error_hint(self, model, raw_error):
        err = str(raw_error).lower()
        hint_lines = []
        if "out of memory" in err or "oom" in err:
            hint_lines.append("Not enough GPU/CPU memory for this model.")
        hint_lines.append(f"Requirements per device:\n"
                          + "\n".join(self._MODEL_HELP.values()))
        hint_lines.append(f"\nTry a smaller model from the tray icon Settings > Model.")
        return "\n".join(hint_lines)

    def _edit_config(self):
        try:
            cf = os.path.expanduser("~/.config/whisper-dictation/config.json")
            subprocess.Popen(['xdg-open', cf])
        except Exception as e:
            print(f"Failed to open config file: {e}", flush=True)

    def start_app(self):
        if self.started: return
        print('Listening...', flush=True)
        self.started = True
        self.recorder.start(self.current_lang)
        self.item_start.set_sensitive(False)
        self.item_stop.set_sensitive(True)
        self._update_icon()
        self._start_timer()

    def stop_app(self):
        if not self.started: return
        if self.timer: self.timer.cancel()
        print('Transcribing...', flush=True)
        self.started = False
        self.recorder.stop()
        print('Done.\n', flush=True)
        self.item_start.set_sensitive(True)
        self.item_stop.set_sensitive(False)
        self._update_icon()

    def _start_timer(self):
        self.start_time = time.time()
        if self.max_time:
            self.timer = threading.Timer(self.max_time, lambda: GLib.idle_add(self.stop_app))
            self.timer.start()

    def toggle(self):
        if self.started: self.stop_app()
        else: self.start_app()

    def quit_app(self):
        if self.started: self.stop_app()
        os._exit(0)

# ── CLI ──────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('-m', '--model', default=argparse.SUPPRESS,
                   choices=['tiny','tiny.en','base','base.en','small','small.en','medium','medium.en','large'])
    p.add_argument('-k', '--key', default=argparse.SUPPRESS)
    p.add_argument('-l', '--language', default=argparse.SUPPRESS)
    p.add_argument('-t', '--max-time', type=float, default=argparse.SUPPRESS)
    p.add_argument('-d', '--device', type=int, default=argparse.SUPPRESS)
    p.add_argument('--list-devices', action='store_true')
    p.add_argument('--push-to-talk', action='store_true', default=argparse.SUPPRESS)
    args = p.parse_args()
    if hasattr(args, 'language') and args.language:
        args.language = args.language.split(',')
    return args

if __name__ == '__main__':
    args = parse_args()

    if args.list_devices:
        pa = pyaudio.PyAudio()
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                print(f"  {i}: {info['name']}")
        pa.terminate()
        sys.exit(0)

    # Load config
    config = get_config() if CONFIG_OK else {}
    if config: print(f"Config: {config}", flush=True)

    # Merge: config <- CLI override
    model  = getattr(args, 'model',  None) or config.get('model', 'base')
    device = getattr(args, 'device', None)
    if device is None: device = config.get('device')
    if device is not None: device = int(device)
    max_time = getattr(args, 'max_time', None) or config.get('max_time', 60)
    lang   = getattr(args, 'language', None)
    if lang is None: lang = config.get('language')
    ptt    = getattr(args, 'push_to_talk', None)
    if ptt is None: ptt = config.get('push_to_talk', False)
    ptt = bool(ptt)
    key    = getattr(args, 'key', None) or config.get('key_combination', 'ctrl+shift')

    print(f"-> model={model} device={device} time={max_time}s lang={lang} ptt={ptt}", flush=True)

    model_obj = load_model(model)
    print(f"{model} loaded", flush=True)

    transcriber = SpeechTranscriber(model_obj)
    if CONFIG_OK:
        transcriber.use_clipboard = config.get("use_clipboard", True)
    recorder = Recorder(transcriber, device_index=device)

    app = TrayApp(recorder, lang, max_time, ptt,
                   models=['tiny','base','small','medium','large'])

    # Wire voice language switching
    transcriber.on_language_switch = app._switch_lang
    app.current_model = model
    if CONFIG_OK: app.config = config

    # Save effective config
    if CONFIG_OK:
        update_config(model=model, device=device, max_time=max_time,
                       language=lang if isinstance(lang, str) else (','.join(lang) if lang else None),
                       push_to_talk=ptt, key_combination=key)

    # Start key listener
    app.current_key = key
    app.keylistener = GlobalKeyListener(app, key, push_to_talk=ptt)
    keyboard.Listener(on_press=app.keylistener.on_press,
                     on_release=app.keylistener.on_release).start()

    print(f"Running. Shortcut: {key} ({'push-to-talk' if ptt else 'toggle'})", flush=True)
    print("Left-click tray icon -> Settings for language/model/device", flush=True)

    try:
        Gtk.main()
    except KeyboardInterrupt:
        print("\nBye")
        app.quit_app()
