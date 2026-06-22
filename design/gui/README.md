# GUI design handoff

This folder is the **handoff point for the GUI design**. The design agent produces the visual design
from Part 1 ("GUI design requirements") of the project plan and drops the results here; the GUI is
then implemented from these artifacts (branches `feat/gui-shell` → `feat/manual-coding-integration`).

## Expected contents

Drop any of the following here (subfolders welcome):

- `mockups/` — wireframes / mockups + component states for:
  1. **Dashboard** (task dropdown, subject list build/confirm/save, per-step pipeline status, batch bar)
  2. **Step Runner / Progress** (progress bar, live log, cancel; error state)
  3. **Annotation Editor** (the centerpiece): stacked tracks sharing one time axis (waveform +
     spectrogram + N label tracks), a **selected-label cross-track highlight** state, the right-side
     **Trial Info** panel, and the **error-code palette**
  4. **Settings** (data roots, MFA model location, task→MFA-config map)
  5. **Batch dialog** (subjects × steps progress)
- `interaction-spec.md` — short interaction notes for the editor: zoom/pan (Ctrl/Shift + wheel),
  label create/edit (Ctrl+B, drag boundaries, inline rename, copy/paste), Tab/Shift+Tab navigation,
  selection → trial-info binding, playback (Spacebar).
- `assets/` — exported icons / color tokens / spacing values, if any.

## Constraints (must stay implementable in PySide6 + pyqtgraph)

- Native desktop, **cross-OS**, resizable, keyboard-centric; Audacity-familiar feel.
- The editor is built on pyqtgraph (2D plots, `ImageItem` spectrogram, linked X axes, region items
  for labels). Keep components within Qt-feasible patterns.
- Prioritize information density and precise pointer interactions over marketing polish.

See the full brief in the project plan, "Part 1 — GUI design requirements".
