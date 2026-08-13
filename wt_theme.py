"""Colour schemes and fonts.

Widgets read colours through `c()` and fonts through `ui()` / `clock()` at the
moment they are built, so switching appearance is a matter of calling `apply()`
and rebuilding the window.
"""

import tkinter.font

# Each theme needs: bg (window), panel (inputs, title bar), fg (text),
# dim (secondary text), accent (the primary button), accent_fg (text on it),
# danger (stop button, errors), invalid (field flashed on bad input).
THEMES = {
    "midnight": {
        "label": "Midnight", "bg": "#1e2128", "panel": "#2b303b", "fg": "#e6e9ef",
        "dim": "#8b93a7", "accent": "#3fb950", "accent_fg": "#0d1117",
        "danger": "#e5534b", "invalid": "#4a2b2b",
    },
    "nord": {
        "label": "Nord", "bg": "#2e3440", "panel": "#3b4252", "fg": "#eceff4",
        "dim": "#8fa1b3", "accent": "#88c0d0", "accent_fg": "#2e3440",
        "danger": "#bf616a", "invalid": "#4c3236",
    },
    "forest": {
        "label": "Forest", "bg": "#1b2b22", "panel": "#243a2e", "fg": "#e3f0e7",
        "dim": "#8fae9b", "accent": "#67c37a", "accent_fg": "#10241a",
        "danger": "#d9736a", "invalid": "#402a28",
    },
    "dracula": {
        "label": "Dracula", "bg": "#282a36", "panel": "#3a3d51", "fg": "#f8f8f2",
        "dim": "#9aa0b5", "accent": "#bd93f9", "accent_fg": "#21222c",
        "danger": "#ff5555", "invalid": "#4a2b33",
    },
    "solarized": {
        "label": "Solarized Dark", "bg": "#002b36", "panel": "#073642", "fg": "#eee8d5",
        "dim": "#93a1a1", "accent": "#b58900", "accent_fg": "#002b36",
        "danger": "#dc322f", "invalid": "#3d2220",
    },
    "paper": {
        "label": "Paper (light)", "bg": "#f6f6f3", "panel": "#e4e4dd", "fg": "#1f2328",
        "dim": "#5f6672", "accent": "#2f7d4f", "accent_fg": "#ffffff",
        "danger": "#b42318", "invalid": "#f6d5d1",
    },
    "contrast": {
        "label": "High Contrast", "bg": "#000000", "panel": "#1a1a1a", "fg": "#ffffff",
        "dim": "#c9c9c9", "accent": "#ffd400", "accent_fg": "#000000",
        "danger": "#ff4d4d", "invalid": "#5a0000",
    },
}

# Offered in the font dropdowns, minus any not installed on this machine.
FONT_CHOICES = [
    "Segoe UI", "Calibri", "Arial", "Verdana", "Tahoma", "Trebuchet MS",
    "Georgia", "Times New Roman", "Consolas", "Cascadia Mono", "Cascadia Code",
    "Courier New", "Lucida Console", "Comic Sans MS",
]

DEFAULT_THEME = "midnight"
DEFAULT_UI_FONT = "Segoe UI"
DEFAULT_CLOCK_FONT = "Consolas"

_state = {
    "theme": DEFAULT_THEME,
    "ui_font": DEFAULT_UI_FONT,
    "clock_font": DEFAULT_CLOCK_FONT,
}


def apply(theme=None, ui_font=None, clock_font=None):
    """Set the appearance used by widgets built from now on."""
    if theme in THEMES:
        _state["theme"] = theme
    if ui_font:
        _state["ui_font"] = ui_font
    if clock_font:
        _state["clock_font"] = clock_font


def apply_settings(settings):
    apply(settings.get("theme"), settings.get("ui_font"), settings.get("clock_font"))


def current():
    return dict(_state)


def theme_key():
    return _state["theme"]


def c(key):
    """A colour from the active theme."""
    return THEMES[_state["theme"]][key]


def ui(size, weight="normal"):
    return (_state["ui_font"], size, weight)


def clock(size):
    return (_state["clock_font"], size, "bold")


def available_fonts():
    """The curated list, filtered to what's actually installed.

    Needs a Tk root to exist; falls back to the full list if asked too early.
    """
    try:
        installed = {name.lower() for name in tkinter.font.families()}
    except Exception:
        return list(FONT_CHOICES)
    found = [name for name in FONT_CHOICES if name.lower() in installed]
    return found or list(FONT_CHOICES)


def theme_labels():
    return [t["label"] for t in THEMES.values()]


def key_for_label(label):
    for key, theme in THEMES.items():
        if theme["label"] == label:
            return key
    return DEFAULT_THEME


def label_for_key(key):
    return THEMES.get(key, THEMES[DEFAULT_THEME])["label"]
