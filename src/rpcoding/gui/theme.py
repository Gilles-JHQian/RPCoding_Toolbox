"""Dark/light theme palettes (from the design handoff) and QSS generation.

Colors, spacing and step-state hues come straight from the design tokens in
``design/gui/design_handoff_response_coding_gui/README.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

from rpcoding.core.steps import EffectiveState

DARK: dict[str, str] = {
    "app-bg": "#15171c",
    "panel": "#1b1e25",
    "toolbar": "#1f232b",
    "border": "#2b303a",
    "border-strong": "#39414e",
    "text-pri": "#e7eaf0",
    "text-sec": "#99a2b1",
    "text-ter": "#646d7c",
    "accent": "#4d96ff",
    "accent-soft": "rgba(77,150,255,0.16)",
    "btn-bg": "#262b34",
    "btn-border": "#353c48",
    "lane-bg": "#0e1014",
}

LIGHT: dict[str, str] = {
    "app-bg": "#eceef2",
    "panel": "#ffffff",
    "toolbar": "#f5f6f8",
    "border": "#e3e6ec",
    "border-strong": "#d3d8e0",
    "text-pri": "#1f2430",
    "text-sec": "#5a6473",
    "text-ter": "#8b93a1",
    "accent": "#2f6fe0",
    "accent-soft": "rgba(47,111,224,0.14)",
    "btn-bg": "#ffffff",
    "btn-border": "#d3d8e0",
    "lane-bg": "#f3f5f9",
}

# EffectiveState -> (dark hue, light hue)
_STATE_COLORS: dict[EffectiveState, tuple[str, str]] = {
    EffectiveState.DONE: ("#46b771", "#2f9e5b"),
    EffectiveState.NOT_STARTED: ("#7d8694", "#8b93a1"),
    EffectiveState.BLOCKED: ("#525a68", "#aeb6c2"),
    EffectiveState.NEEDS_MANUAL: ("#9a7be0", "#7c5fd0"),
    EffectiveState.STALE: ("#d6a13a", "#bf8a1f"),
    EffectiveState.ERROR: ("#e5564d", "#d23b32"),
}
_RUNNING = ("#4d96ff", "#2f6fe0")

# Human-facing labels for the state chips.
STATE_LABELS: dict[EffectiveState, str] = {
    EffectiveState.DONE: "Done",
    EffectiveState.NOT_STARTED: "Not started",
    EffectiveState.BLOCKED: "Blocked",
    EffectiveState.NEEDS_MANUAL: "Needs manual",
    EffectiveState.STALE: "Stale",
    EffectiveState.ERROR: "Error",
}


@dataclass(frozen=True)
class Theme:
    name: str  # "dark" | "light"
    palette: dict[str, str]

    def color(self, key: str) -> str:
        return self.palette[key]

    def state_color(self, state: EffectiveState) -> str:
        idx = 0 if self.name == "dark" else 1
        return _STATE_COLORS.get(state, _RUNNING)[idx]


DARK_THEME = Theme("dark", DARK)
LIGHT_THEME = Theme("light", LIGHT)
THEMES = {"dark": DARK_THEME, "light": LIGHT_THEME}


def qss(theme: Theme) -> str:
    """Application-wide stylesheet for a theme."""
    p = theme.palette
    return f"""
    QWidget {{ background: {p['app-bg']}; color: {p['text-pri']};
               font-family: "Segoe UI", "IBM Plex Sans", sans-serif; font-size: 13px; }}
    QFrame#Panel, QListWidget {{ background: {p['panel']}; border: 1px solid {p['border']};
                                 border-radius: 9px; }}
    QFrame#TopBar {{ background: {p['toolbar']}; border-bottom: 1px solid {p['border']}; }}
    QLabel#SubjectId {{ font-size: 18px; font-weight: 600; }}
    QLabel#Secondary {{ color: {p['text-sec']}; }}
    QLabel#Meta {{ color: {p['text-ter']}; font-size: 11px; }}
    QPushButton {{ background: {p['btn-bg']}; border: 1px solid {p['btn-border']};
                   border-radius: 6px; padding: 5px 12px; }}
    QPushButton:hover {{ border-color: {p['accent']}; }}
    QPushButton:disabled {{ color: {p['text-ter']}; }}
    QPushButton#Primary {{ background: {p['accent']}; border: none; color: white;
                           font-weight: 500; }}
    QComboBox, QLineEdit {{ background: {p['btn-bg']}; border: 1px solid {p['btn-border']};
                            border-radius: 6px; padding: 4px 8px; }}
    QListWidget::item:selected {{ background: {p['accent-soft']};
                                  border-left: 3px solid {p['accent']}; }}
    QPlainTextEdit {{ background: {p['lane-bg']}; border: 1px solid {p['border']};
                      border-radius: 6px; font-family: "IBM Plex Mono", Consolas, monospace; }}
    """
