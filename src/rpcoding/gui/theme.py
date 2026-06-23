"""Dark/light theme palettes (from the design handoff) and QSS generation.

Colors, spacing and step-state hues come straight from the design tokens in
``design/gui/design_handoff_response_coding_gui/README.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

from rpcoding.core.steps import EffectiveState

# Font stacks: prefer the IBM Plex families (design), fall back to OS-native + a mono.
UI_FONT = '"IBM Plex Sans", "Segoe UI", system-ui, sans-serif'
MONO_FONT = '"IBM Plex Mono", "Cascadia Mono", Consolas, monospace'


def soft_rgba(hex_color: str, alpha: float = 0.15) -> str:
    """A translucent ``rgba(...)`` of a ``#rrggbb`` color, for chip / dot fills."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


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
    "wave-stroke": "#46c7d6",
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
    "wave-stroke": "#1693a0",
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
    EffectiveState.NEEDS_MANUAL: "Manual",
    EffectiveState.STALE: "Stale",
    EffectiveState.ERROR: "Error",
}
RUNNING_LABEL = "Running"


@dataclass(frozen=True)
class Theme:
    name: str  # "dark" | "light"
    palette: dict[str, str]

    def color(self, key: str) -> str:
        return self.palette[key]

    def state_color(self, state: EffectiveState) -> str:
        idx = 0 if self.name == "dark" else 1
        return _STATE_COLORS.get(state, _RUNNING)[idx]

    def running_color(self) -> str:
        return _RUNNING[0 if self.name == "dark" else 1]


DARK_THEME = Theme("dark", DARK)
LIGHT_THEME = Theme("light", LIGHT)
THEMES = {"dark": DARK_THEME, "light": LIGHT_THEME}


def qss(theme: Theme) -> str:
    """Application-wide stylesheet for a theme (design tokens in the handoff README)."""
    p = theme.palette
    return f"""
    QWidget {{ background: {p['app-bg']}; color: {p['text-pri']};
               font-family: {UI_FONT}; font-size: 13px; }}
    QFrame#Panel {{ background: {p['panel']}; border: 1px solid {p['border']};
                    border-radius: 9px; }}
    QFrame#SidePanel {{ background: {p['panel']}; border: none;
                        border-right: 1px solid {p['border']}; }}
    QFrame#TopBar {{ background: {p['toolbar']}; border: none;
                     border-bottom: 1px solid {p['border']}; }}
    QFrame#PanelHeader {{ background: {p['app-bg']}; border: none;
                          border-bottom: 1px solid {p['border']}; }}
    QFrame#HLine {{ background: {p['border']}; max-height: 1px; min-height: 1px; border: none; }}

    QLabel#SubjectId {{ font-family: {MONO_FONT}; font-size: 18px; font-weight: 600; }}
    QLabel#SectionTitle {{ font-size: 13px; font-weight: 600; }}
    QLabel#Secondary {{ color: {p['text-sec']}; }}
    QLabel#Meta {{ color: {p['text-ter']}; font-family: {MONO_FONT}; font-size: 11px; }}
    QLabel#Mono {{ font-family: {MONO_FONT}; }}
    QLabel#Banner {{ font-size: 12px; }}

    QPushButton {{ background: {p['btn-bg']}; border: 1px solid {p['btn-border']};
                   border-radius: 7px; padding: 6px 13px; color: {p['text-sec']}; }}
    QPushButton:hover {{ border-color: {p['accent']}; color: {p['text-pri']}; }}
    QPushButton:disabled {{ color: {p['text-ter']}; border-color: {p['border']};
                            background: {p['app-bg']}; }}
    QPushButton#Primary {{ background: {p['accent']}; border: none; color: #ffffff;
                           font-weight: 600; padding: 8px 16px; }}
    QPushButton#Primary:hover {{ background: {p['accent']}; }}
    QPushButton#Icon {{ padding: 7px 11px; }}

    QComboBox, QLineEdit {{ background: {p['btn-bg']}; border: 1px solid {p['btn-border']};
                            border-radius: 7px; padding: 6px 11px; color: {p['text-pri']}; }}
    QComboBox {{ font-family: {MONO_FONT}; }}
    QComboBox QAbstractItemView {{ background: {p['panel']}; border: 1px solid {p['border-strong']};
                                   selection-background-color: {p['accent-soft']}; outline: none; }}

    QListWidget {{ background: {p['panel']}; border: none; outline: none; }}
    QListWidget::item {{ border: none; padding: 0px; }}
    QListWidget::item:selected {{ background: transparent; }}

    QScrollArea {{ background: {p['app-bg']}; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {p['border-strong']}; border-radius: 5px;
                                   min-height: 28px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

    QPlainTextEdit {{ background: {p['lane-bg']}; border: 1px solid {p['border']};
                      border-radius: 7px; font-family: {MONO_FONT}; }}
    QToolTip {{ background: {p['toolbar']}; color: {p['text-pri']};
                border: 1px solid {p['border-strong']}; padding: 5px 8px; }}
    """
