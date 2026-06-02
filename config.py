#!/usr/bin/env python3
"""
Configuration management for whisper-dictation
Loads/saves settings from ~/.config/whisper-dictation/config.json
"""

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "whisper-dictation"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "model": "base",
    "device": None,  # Auto-detect if None
    "max_time": 60,
    "language": "en",
    "push_to_talk": False,
    "key_combination": "ctrl+shift"
}

def load_config():
    """Load configuration from file, or return defaults if not exists"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # Merge with defaults to ensure all keys exist
                merged = DEFAULT_CONFIG.copy()
                merged.update(config)
                return merged
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load config: {e}")
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()

def save_config(config):
    """Save configuration to file"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def get_config():
    """Get current configuration (load if not already in memory)"""
    if not hasattr(get_config, '_cached'):
        get_config._cached = load_config()
    return get_config._cached

def update_config(**kwargs):
    """Update configuration and save to file"""
    config = get_config()
    config.update(kwargs)
    save_config(config)
    get_config._cached = config
    return config

def reset_config():
    """Reset configuration to defaults"""
    save_config(DEFAULT_CONFIG.copy())
    get_config._cached = DEFAULT_CONFIG.copy()

if __name__ == "__main__":
    # Test
    print("Current config:", get_config())
    update_config(model="small", max_time=30)
    print("Updated config:", get_config())
