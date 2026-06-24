# Changelog

All notable changes to RPCoding Toolbox. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project is pre-release (`0.1.0`,
in development); entries are grouped by the feature branch that delivered them, newest first.

## [Unreleased]

### Backend — pipeline core (golden-file verified)

- **Scaffolding & environment** (`feat/scaffolding`): src layout, `pyproject.toml`, cross-platform
  `environment.yml` + `scripts/setup_env.{ps1,sh}`, ruff/black/pre-commit, pytest skeleton, the
  core-has-no-Qt guard, CI matrix, and the `design/gui/` handoff path.
- **Core I/O** (`feat/core-io`): `AppConfig`/paths/`Task` enum + MFA map; `labels.Tier` Audacity
  `.txt` read/write; `matio` `.mat` load/save with the cell-vs-struct + field-name "ladders";
  Word/Nonword classification.
- **WAV concat** (`feat/wav-concat`): `combine_wavs` port — block order, 10 s pad, 1-based onsets,
  equal-fs assert; soundfile IO.
- **trialInfo merge** (`feat/trialinfo-merge`): combine/fix/cell2mat ports; the **D140/D134**
  split-run detector that reconstructs the full 504-trial list (byte-exact vs MATLAB); provenance
  report.
- **Event generation** (`feat/event-generation`): `make_cue_events` + `make_condition_events` ports;
  reads the external `Trials.mat` (`.Auditory`); hard error if missing/ambiguous.
- **Project session** (`feat/project-session`): the Step DAG + staleness, `SubjectSession` +
  atomic `Manifest`, subject scanner, batch runner, and the headless CLI.
- **MFA integration** (`feat/mfa-integration`): vendored the lab's MFA pipeline; model/dict download
  helper; runner via `sys.executable`; `mfa_*.txt` ingest.
- **rpcode2trials** (`feat/rpcode2trials`): the `bsliang_rpcode2trials` port — EDF realignment,
  NoDelay/Delay branches, derived error tags; normal path only; per-branch + `Trials.mat` goldens.

### GUI

- **Shell** (`feat/gui-shell`): QApplication + main window, task/subject panel, worker base +
  progress dialog, dashboard step status, dark/light theme.
- **Audio render engine** (`feat/audio-render-engine`): waveform min/max LOD pyramid + cache;
  memmapped log-spectrogram (Magma + HistogramLUT); shared x-linked time axis. Real-data verified
  (~6 s build, <15 ms reslice on a 50.9-min file).
- **Label tracks** (`feat/label-tracks`): tier rendering, cross-lane selection highlight, Trial Info
  panel, keyboard editing (Ctrl+B / Tab / Delete).
- **Manual-coding integration** (`feat/manual-coding-integration`): editor loads real tiers per step;
  saves `first_stims.txt` / `bsliang_resp_words_errors.txt`; wires the `write_trials` step (enriched
  `Trials.mat` + `Trials_org.mat` backup); `AppConfig` word/nonword lists.
- **Batch & polish** (`feat/batch-and-polish`): batch dialog (automated pipeline across selected
  subjects, aggregated progress); settings dialog (data root, word lists, MFA task map); optional
  external-denoise step; the [User Guide](docs/USER_GUIDE.md).

### Dashboard V0.2 (`feat/dashboard-v0.2`)

- **File-based step completion:** a step shows Done when its output exists on disk, even with no
  manifest — subjects processed by the legacy pipeline now show green. Disk presence wins over a
  leftover error record.
- **Cloud-sync resilience:** stat/exists calls swallow `OSError`, so an un-readable Box placeholder
  (WinError 1006) no longer crashes the scan.
- **UX fixes from V0.1 testing:** task switch auto-rescans; single steps run inline (no popup) with a
  *Running* chip; errors are re-runnable, hover-summarised and click-to-detail; subject rows show
  file-based `done/total`.
- **Visual rebuild to the design handoff:** IBM Plex fonts, filled-pill state chips + status dots,
  subject-list rows, mono subject-id header with a stale/complete banner, per-state action buttons.

### Editor performance & interaction (`fix/editor-performance`, `fix/editor-interaction`)

- **Label virtualization:** only the labels in view are rendered (recycled pool, capped); the
  response-coding editor no longer freezes/crashes on the thousands-of-intervals tiers (a working
  window renders in ~2–15 ms). The dense `*_phones` MFA tiers are excluded.
- **Unified interaction across all lanes:** one `InteractiveViewBox` on every track — left-drag
  selects a span (→ Ctrl+B labels), **Ctrl+wheel** zooms, **Shift+wheel** pans (plain wheel no-op),
  working over the waveform, spectrogram and label tracks alike.
- **Label selection** (`feat/label-selection`): click a label to select it — then drag the whole
  body or either endpoint, **Enter** to rename, click an **error-palette** code to append it, or
  **Delete** to remove it. The selected label's time span highlights across the waveform and
  spectrogram.
- **Tab/cursor/selection polish** (`feat/editor-tab-cursor-compat`): **Tab/Shift+Tab** navigate
  labels (intercepted before Qt's focus traversal; toolbar/palette buttons no longer steal it).
  Clicking an audio lane drops a **cursor**; a left-drag **inside** the current selection moves it,
  a drag **outside** starts a new one (Audacity-style).
- **Clipboard, undo/redo, resizable selection, live drag** (`feat/editor-clipboard-undo`): label
  **copy / cut / paste** (Ctrl+C/X/V — paste lands at the cursor/selection, keeping duration + text)
  and **undo/redo** (Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z) over the editable tier. The selection span is
  now **resizable** — drag its body to move, an edge to resize, on the waveform or spectrogram. And
  while you drag a label, its cross-lane highlight follows in **real time** (not only on release).
- **Unified editor + display polish** (`feat/editor-unified-readout`): both manual steps now use one
  lane layout — first stim · condition · cue · response — toggling only which lane is editable (the
  response lane starts from the saved coding, else the MFA response words). The selection readout is
  **editable** (type a precise start/end in seconds). The waveform is shorter and the spectrogram
  taller; the waveform amplitude **auto-scales** to a robust percentile of the signal (ignoring click
  transients), and the spectrogram's default dB window is raised for a cleaner, less-bright view.
- **Audio playback** (`feat/editor-playback`): **Space** / the **▶ Play** button plays the audio;
  a selection plays that span, else a cursor plays from there to the end, else the whole file; Space
  again stops. Streams from the wav via sounddevice (any range, no RAM blow-up) and stops on close.
  Gracefully a no-op when there's no audio backend.
- **Playback controls** (`feat/editor-playback-controls`): a **Vol** slider sets the playback gain
  (independent of the waveform display amplitude). The **cursor doubles as the playhead** — it tracks
  playback, the view auto-scrolls to keep it visible, and on stop the cursor is left exactly where
  playback paused (so Space resumes from there).

### Data compatibility

- **Tolerant block-folder lookup** (`feat/editor-tab-cursor-compat`): the per-block wavs/mats aren't
  always in `<subj>/Lexical No Delay/All Blocks` — the task folder may be `Lexical`, the block
  folder a (possibly nested) timestamped session, and the same folder mixes practice + per-trial
  files. `resolve_blocks_dir` now narrows to the task group, disambiguates the session by keyword
  (NoDelay vs Delay), and ignores practice; block-wav discovery skips per-trial (`*_Trial_<n>*`) and
  practice files. Verified on D24/D26/D27 (three different layouts).
- **Editor is its own window**; opens zoomed to the first 60 s for a fast first render (Fit shows the
  whole file); horizontal track names in a left column; label lanes drop the y-axis ticks.
- **Non-blocking dashboard scan:** per-subject summaries computed incrementally via a `QTimer`.

### Fixed

- **Editor crash on open** (`fix/editor-thread-crash`): render-worker `result` signals were Direct
  connections, so the pyqtgraph reslice ran on the worker thread; after virtualization this created
  `TextItem`s off the GUI thread → access violation (both workers racing the same lane pool). Results
  are now routed through queued editor signals so the graphics work runs on the UI thread.

## Deferred

- **Irregular subjects** (`feat/irregular-subjects`): per-subject MATLAB corrections
  (D90/D28/D26/D92/D100/D102/D117/D23) and lenient count-mismatch recovery — awaiting rules/data.
