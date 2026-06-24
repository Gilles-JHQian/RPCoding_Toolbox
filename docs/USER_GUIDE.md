# RPCoding Toolbox — User Guide

A guided, cross-platform desktop app that runs the Cogan Lab **Response Coding** preprocessing
pipeline: automated steps batch across subjects; the two manual steps are done in a built-in,
Audacity-like waveform/spectrogram label editor. Outputs faithfully reproduce the legacy
MATLAB + Audacity + MFA results.

## 1. First launch

1. Activate the env and start the app:
   ```bash
   conda activate rpcoding
   rpcoding-gui
   ```
2. On first run you are asked for the **CoganLab data root** (`$BOX/CoganLab`). This is remembered
   in your per-user config (`%APPDATA%\rpcoding\config.json` on Windows,
   `~/.config/rpcoding/config.json` elsewhere).
3. Open **⚙ Settings** to finish configuration (see below). The **Write Trials** step needs the
   word / nonword lists set, so configure them before running the full pipeline.

## 2. Settings (⚙)

| Field | Meaning |
|---|---|
| **Data root** | `$BOX/CoganLab`. The `D_Data`, `ECoG_Task_Data`, and results trees are derived from it. |
| **Word list** / **Nonword list** | The lab's `word_lst.mat` / `nonword_lst.mat` (variables `words` / `nonwords`). Required by **Write Trials** to classify each stimulus as Word/Nonword. |
| **MFA task config** | Per task, the MFA pipeline config name. Defaults: `LexicalDecRepNoDelay → lexical_repeat_no_delay`, `LexicalDecRepDelay → lexical_repeat`. `Uniqueness_Point` is unmapped until you supply its config. |

Settings are saved immediately and applied to the currently selected subject.

## 3. Dashboard

1. Pick a **Task** (top-left). The **◑** button toggles the light/dark theme.
2. **Scan subjects** lists the `D<number>` / `S<number>` folders under `D_Data/<task>`. Each is
   checkable; uncheck any you want to exclude from a batch run — the header shows
   **"N found · K selected"**. The **checkbox next to "Subjects"** selects / deselects all at once.
   Use the **filter** box to narrow the list, and **＋ / －** to add a subject by ID (typed in the
   filter box) or remove the selected one. **Save list** remembers the checked subjects for that task
   and restores them on the next scan.
3. Select a subject to see its **pipeline status** — one row per step with a state chip:
   - `Not started` · `Blocked` (waiting on an upstream step) · `Needs manual` · `Done` ·
     `Stale` (an upstream output changed since this step ran) · `Error`.
4. Each automated step has a **Run / ↻ Re-run** button; manual steps have a purple **Open editor**.

### Pipeline steps (in order)

1. **Create results folder**
2. **Concatenate WAVs** → `allblocks.wav` (+ `block_wav_onsets.mat`)
3. **Build trialInfo.mat** (auto-merges incomplete blocks, e.g. split-run subjects)
4. **Denoise** *(optional, external)* — denoise `allblocks.wav` in Audacity, then click Run to mark
   it acknowledged. Skipped by batch runs.
5. **Mark first stimuli** *(manual)* → `first_stims.txt`
6. **Generate cue + condition events** → `cue_events.txt`, `condition_events.txt`
7. **MFA forced alignment** → `mfa/mfa_*.txt`
8. **Manual response coding** *(manual)* → `bsliang_resp_words_errors.txt`
9. **Write response coding → Trials.mat** (backs up `Trials_org.mat`, writes the enriched
   `Trials.mat` into `D_Data/**/mat/`)

> **Trials.mat is a required input.** If it's missing or ambiguous (more than one match under
> `D_Data/<task>/<subj>/**/mat/`), the affected steps stop with a clear error.

## 4. Batch run (▶ Run batch)

Runs the **automated** steps for every checked subject, in order, stopping each subject at its first
manual/blocked step. A table shows per-subject progress (`✓ ran` / `✗ <error>`); already-completed
steps are skipped. Manual steps and the optional denoise step are not run by batch.

## 5. Annotation editor

Opened from a manual step. The window has three columns: a **left header column** with each track's
name and controls, the **plot column** (a shared time axis with a **waveform** lane, a **spectrogram**
lane, and four label tracks — **first stim · condition · cue · response**), and a right **Trial Info**
panel. Only the editable track differs by step:

- **Mark first stimuli**: the `first stim` track is editable (the rest are read-only reference).
- **Response coding**: the `response` track is editable; it starts from your saved coding, else the
  MFA-aligned response words, else empty.

Drag/zoom/pan work over **any** lane. Selecting a span — or a label — shows the trial it maps to in
the Trial Info panel and highlights that time across all lanes. The selection readout in the toolbar
is **editable**: click the start/end field to type a precise time (seconds).

**Cursor & selection:** click an audio lane to drop a cursor; left-drag to select a span. Once a span
exists, dragging **inside** it moves the whole selection, dragging an **edge** resizes it, and
dragging **outside** starts a new one (Audacity-style).

**Selecting & editing labels:** click a label to select it; then drag its body or either endpoint to
adjust (the highlight follows live), press **Enter** to rename, or click an **error-palette** button
(right panel) to append that code. With a label selected the toolbar readout switches to **"label"**
and shows its start / end / length — **typing a new start or end retimes the label itself** (a precise
alternative to dragging). **Ctrl+C / Ctrl+X / Ctrl+V** copy / cut / paste a label (paste lands at the
cursor, keeping its length), and **Ctrl+Z / Ctrl+Y** undo / redo. The selected label's span is
highlighted on the waveform and spectrogram above.

**Playback:** **Space** (or the **▶ Play** button) plays the audio — if a selection/label is active it
plays that span; otherwise if a cursor is set it plays from there to the end; otherwise the whole
file. Space (or the button) again stops. The **cursor follows playback** (the view auto-scrolls to
keep it in view) and is left where you stopped, so Space resumes from there. Clicking the timeline
**while playing seeks** — playback continues from where you click. The **Vol** slider (toolbar) sets
the playback volume (up to 10× for quiet recordings); the **amp ＋/－** buttons in the waveform's
header scale only the waveform's on-screen height.

The editor follows the **light/dark theme** — toggle it from the dashboard or the **◑** button in the
editor toolbar. When the time axis is zoomed so a label is narrower than its text, the text truncates
with **…** inside the chip; **hover the label** to see its full text.

### Keyboard / mouse

| Shortcut | Action |
|---|---|
| Space / ▶ Play | Play / stop (selection span · cursor-to-end · whole file) |
| Ctrl + wheel | Zoom the time axis about the cursor |
| Shift + wheel | Pan the time axis |
| Left-drag (any lane) | Select a time span |
| Click a label | Select it (then drag / Enter-rename / error-palette) |
| Drag selection edge / body | Resize / move the selection |
| Ctrl + B | Create a label from the selection (on the editable track) |
| Enter | Rename the selected label |
| Ctrl + C / X / V | Copy / cut / paste the selected label |
| Ctrl + Z / Y | Undo / redo label edits |
| Tab / Shift+Tab | Next / previous label on the editable track |
| Delete / Backspace | Delete the selected label |
| 🔍＋ / 🔍－ / Fit | Zoom in / out / show the whole file |
| Ctrl + S | Save the editable track |
| Esc | Close the editor |

**Save** writes the editable track to its Audacity-compatible `.txt` (`start⇥end⇥label`, seconds)
and marks the step done on the dashboard. Use **← Back** or **Esc** to return.

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| *"Word/nonword lists are not configured"* on Write Trials | Set both lists in ⚙ Settings. |
| *"No Trials.mat under …"* / *"more than one Trials.mat"* | The upstream `Trials.mat` is required and must be unique under `D_Data/<task>/<subj>/**/mat/`. |
| MFA step errors | Confirm the task is mapped in Settings and the MFA models/dictionary are installed (`scripts/setup_env.*`). The app stays usable — you can drop `mfa/*.txt` in by hand and continue. |
| A step shows **Stale** | An upstream output changed since this step ran (e.g. you re-edited `first_stims.txt`). Re-run it. |
| Subject won't scan | Check the **Data root** in Settings and that `D_Data/<task>` exists. |

## 7. Headless / CLI

The core pipeline is pure Python and runs without the GUI. All commands take
`--droot <CoganLab root>` and `--task <task id>`:

```bash
rpcoding scan     --droot "$BOX/CoganLab" --task LexicalDecRepNoDelay
rpcoding status   --droot "$BOX/CoganLab" --task LexicalDecRepNoDelay D134
rpcoding run      --droot "$BOX/CoganLab" --task LexicalDecRepNoDelay D134 [--force]
rpcoding run-step --droot "$BOX/CoganLab" --task LexicalDecRepNoDelay D134 concat_wavs
rpcoding batch    --droot "$BOX/CoganLab" --task LexicalDecRepNoDelay [--subjects D133,D134]
```

`run` / `batch` execute the automated steps only, stopping at manual steps — use this for scripted
processing on a server. `run-step` runs a single step by id (`create_results`, `concat_wavs`,
`build_trialinfo`, `denoise`, `make_events`, `run_mfa`, `write_trials`).
