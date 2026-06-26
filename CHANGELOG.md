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

### Step progress bars (`feat/step-progress`)

- **A real progress system, end to end.** A lightweight `core/progress.py` (`Reporter` =
  `callable(fraction, message)`; `StepProgress` for pipeline-level position) flows from the step
  actions up through `run_step` / `run_pipeline` / `run_batch` to the GUI. Each automated step now
  reports its phases: concatenation ticks per block read; events / write-Trials report their
  load→compute→save phases; MFA surfaces its live stdout (banner stages bump a coarse fraction,
  other lines scroll as the message) so you can see *where* the long alignment step is.
- **Inline per-step bar on the dashboard:** while a step runs, its row shows a thin bar (just left
  of the state chip, on the step's second line) plus the live phase text — determinate where the
  fraction is known, indeterminate (busy) otherwise. Delivered on the GUI thread via a queued signal.
- **Aligned status column:** the state chips and action buttons are now fixed-width, so *Done* /
  *Not started* / *Manual* / *Stale* line up in tidy columns across the step list.
- **Detailed batch dialog:** each subject row shows its **current step + phase** and a per-subject
  bar; a fine-grained footer bar tracks overall progress (subjects done + the running subject's
  within-pipeline fraction) instead of just whole-subject counts.

### Uniqueness Point — MFA support (`feat/uniqueness-point-mfa`)

First steps toward running the pipeline on the Uniqueness Point (UP) task; this enables **MFA** on
UP (downstream `rpcode2trials` / word-lists are still lexical-only and come later).

- **Custom pronunciation dictionary.** UP's 40 nonwords are pseudowords absent from
  `english_us_arpa`, so MFA couldn't align the responses. `core/mfa/up_dict.py` assembles
  `english_us_up.dict` (80 tokens) straight from each token's existing `*_phones.txt` ARPABET
  annotation — robust to the files' inconsistent format (some carry a word-level row, some don't).
  The dict is vendored and auto-installs via the existing `*.dict` glob (re-run the Settings MFA
  install, or `python -m rpcoding.core.mfa.models --ensure-models`).
- **Task config `uniqueness_point.yaml`** wired into the task map (`Uniqueness_Point →
  uniqueness_point`). `mark_yes_no: False` (Yes/No is a button press in UP; only Repeat responses
  are aligned).
- **Nested stim annotations.** UP stores each token's annotations in its own subfolder
  (`stim_annotations/<token>/<token>_{words,phones}.txt`) rather than flat. A `stim_nested` task
  flag makes `loadAnnotsToDict` look one level deeper — **UP-only**, lexical tasks read flat as
  before. (Marked TODO: remove once the dataset is flattened.)

### Denoise — noise-profile reduction (`feat/editor-denoise`)

- **Real noise reduction in the editor**, replacing the placeholder (which only marked the step
  done). Audacity's two-step flow: select a noise-only span and click **🔇 Noise profile**, set a
  **strength** (0–100%), then **Denoise** — spectral subtraction (`noisereduce`) across the whole
  recording. `core/audio/denoise.py` always works from the *raw* signal (preserved once as
  `allblocks_original.wav`), so re-applying at a different strength never compounds; the result is
  written to `allblocks.wav` and the editor reloads it. Runs on a worker thread (GUI stays
  responsive); the Denoise step opens the editor and is marked done once reduction is applied.

### UX: loading feedback + hover cursors (`feat/loading-and-cursor`)

- **Loading popups.** A small `LoadingDialog` (progress bar) now appears (a) on app **startup**
  while the main window is built (so launch isn't a blank wait), and (b) when **opening the editor**
  — the editor stays hidden and a popup tracks the waveform/spectrogram render (driven by a new
  `load_progress` signal), revealing the editor once it's ready. The open popup is delayed ~180 ms so
  a cached, instant open doesn't flash it.
- **Pointing-hand cursor on hover.** An app-wide event filter (`hover_cursor.py`) gives every
  clickable widget (buttons, combo boxes) the hand cursor on mouse-over (and the plain arrow when
  disabled) — covering dynamically created controls that a stylesheet can't reach.

### Subject notes, problem flag, folder shortcuts + first-run dialog (`feat/subject-gadgets`)

- **Current-step column.** Each subject in the list now shows which step it's at — the first
  required step not yet done (e.g. "MFA", "Response", "✓ done") — next to its done/total, via a new
  one-pass `SubjectSession.status()`.
- **Per-subject notes.** Selecting a subject shows a free-text notes field (behavioural coding is
  messy and per-subject state varies); notes are saved (debounced) into the subject's manifest.
- **Manual "has a problem" flag.** A new ⚑ Flag toggle marks a subject as problematic — a distinct
  rose/pink state (`EffectiveState.FLAGGED`) that takes precedence over the computed status in the
  subject list dot + the detail banner. Stored in the manifest.
- **Folder shortcuts.** The status-bar button is now a 📂 Folders menu opening any of the subject's
  key folders — results, the D_Data folder (Trials.mat), the raw audio blocks, and the data root —
  greying out the ones that don't exist yet.
- **First-run dialog.** First launch (or a missing saved data root) now shows an explanation of
  *what* to pick — the CoganLab data root containing `D_Data` / `ECoG_Task_Data` — with a
  **Choose folder…** button, instead of popping a bare folder picker with no context. It softly
  warns if the chosen folder doesn't look like a CoganLab root, but still lets you continue.
- **Cross-OS review.** Audited the app code for OS-specific assumptions: paths are all `pathlib`,
  folders open via `QDesktopServices` (Explorer/Finder/file-manager), the config dir already
  branches APPDATA vs XDG, and no drive letters / backslash paths are hardcoded. The MFA pipeline's
  earlier Windows-isms were already fixed (`resolve_stim_dir`, aligner PATH, trailing-dot).
- **Optional steps don't block completion.** The optional Denoise step no longer counts toward a
  subject's done/total — a subject shows green once every *required* step is done, whether or not
  Denoise ran (`SubjectSession.summary()` + the detail banner judge required steps only).

### Faster startup (`perf/lazy-startup`)

- **The audio editor is built lazily on first open, not at launch.** Profiling showed startup was
  dominated by the editor's imports — `import pyqtgraph` (~0.17 s) + `import scipy.signal` (~0.5 s)
  — plus ~0.26 s constructing it, all paid before the window even appeared (and far worse on
  low-end machines / cold disk). The editor is the *only* thing that needs those; the dashboard
  doesn't. `MainWindow` now constructs the editor on the first **Open editor** (a popup shows during
  that one-time import/build), so launch no longer loads pyqtgraph/scipy.signal at all — verified by
  a regression test. Warm `import rpcoding.gui.app` dropped ~1000 ms → ~390 ms; `MainWindow(...)`
  ~108 ms → ~48 ms.
- **The pipeline action chain is imported lazily too.** The dashboard no longer pulls
  `core.runner` (combine-wavs / trialInfo / MFA / rpcode2trials) or the batch dialog at import; they
  load when a step actually runs or the batch dialog opens.

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
- **Editor look + theme fix** (`feat/editor-theme-labels`): the editor now fully follows the design
  tokens in **both** light and dark — fixing the bug where the editor background stayed dark in light
  mode (the plot surface, lane fills, track names, selection/cursor all re-theme now). Labels are
  styled as chips (`label-bg`/`label-border`/`label-text`), the response lane is tinted. When the time
  axis is zoomed so a label is too narrow for its text, the **text drops just below the label** (and
  sits on it when it fits). The **Vol** slider now goes to **10x** with a live readout (quiet
  recordings needed more headroom).
- **Below-lane label text + click-to-seek** (`fix/editor-label-seek`): a too-narrow label's text now
  drops into the **gap below the whole track** (clipping disabled + a per-lane gap), instead of the
  lane's bottom edge where it still overlapped the chip; the text layer is also forced **above** the
  chip shape (z-order). And clicking the timeline **while playing now seeks** — playback continues
  from the click point instead of the playhead overwriting it (the player tears the old stream down
  silently on a re-`play()` so the UI keeps its playing state).
- **Editor rebuilt to the HTML prototype** (`feat/editor-html-redesign`): the editor now matches
  `design/gui/.../02 Annotation Editor.dc.html`. A dedicated **170px header column** (panel) holds
  each track's name + sub-label, the waveform **amp ＋/－** control, and a focus rail that follows the
  selected lane; it is kept pixel-aligned with the pyqtgraph plot rows (identical fixed heights, zero
  layout spacing, a reserved bottom-stretch row — and the spectrogram histogram is height-capped so it
  can't inflate its row). The plot column is the `lane-bg` surface (ruler/waveform/spectrogram/lanes);
  the toolbar gains **＋ Label** (accent), **Copy/Paste**, and a **◑ theme toggle**, keeps **Vol**, and
  drops the amp slider (moved to the header). Label chips are **flush** (no inter-lane gaps): a chip
  too narrow for its text truncates with `…` and the **full label shows on hover** (replacing the
  earlier below-the-lane text). The Trial Info panel gains the **error-palette caption** and the
  **labeling-conventions hint**, with the Error value in the danger color.
- **Dashboard polished to the HTML prototype** (`feat/dashboard-html-polish`): a multi-lens gap
  analysis drove the editor-matching visual pass over `design/gui/.../03 Dashboard.dc.html`. Top bar
  gains a **Save list** button and a labelled **◑ Light/Dark** theme toggle (flips with the theme);
  the subject panel gains a **filter row** (filter box + ＋/－ add/remove) and a **"N found · K
  selected"** count. Subject rows use a true **9px state dot**; step rows show an inline purple
  **manual** tag, **monospace filenames** in titles (the step titles now read `… → allblocks.wav` /
  `first_stims.txt` / `Trials.mat`), a 12px/600 mono index, and a neutral (not red) error action.
  State **chips** are capsules with a real 7px colored dot, and dots/chips use the prototype's
  per-theme soft-fill alpha (`Theme.soft_alpha`). Button/combobox paddings, header backgrounds, and
  a bottom-centre **toast** (used by Save list) round it out. **Save list** persists the checked
  subjects per task and restores them on the next scan.
- **Select-all + no more label boxes** (`fix/dashboard-labels-select-all`): a **tri-state select-all
  checkbox** in the Subjects header checks/unchecks every subject at once (and shows partial). Fixed
  the ugly dark boxes behind plain text labels — the global `QWidget { background: app-bg }` was
  cascading an opaque app-bg fill onto every `QLabel` (visible over the panel/toolbar); labels are now
  `background: transparent` by default, while the state dots, chips, and toast keep their own fills.
- **Retime a selected label from the toolbar** (`fix/label-retime-and-mfa-dep`): selecting a label now
  retitles the toolbar readout to **"label"** and shows its start / end / length; typing into the
  start/end fields **retimes the label itself** (not just the free selection), with the mirrored
  selection following along. `LabelLane.resize_active` records it for undo.
- **MFA setup panel in Settings** (`feat/settings-mfa-check`): the Settings dialog now has a
  **Montreal Forced Aligner** section that probes the install — engine (`mfa`), acoustic model,
  base + custom dictionaries, and the `noisereduce` denoise dep — and shows each as ✓/✗. A
  **Download & install models** button runs `ensure_mfa_setup` (pip-installs missing pipeline deps,
  `mfa model download`, installs the vendored custom dicts) off the UI thread, with a **Re-check**
  button. New `mfa_status()` / `ensure_mfa_setup()` in `core/mfa/models.py`.
- **Tab navigates the *focused* track** (`fix/editor-tab-focus`): `Tab` / `Shift+Tab` now step through
  labels on whichever track you've selected (click a label, or `Up`/`Down` to move between tracks),
  instead of always snapping back to the editable track. Both manual editors now behave identically —
  they just open focused on their editable track (first-stims vs response). Split the "focused track"
  (navigation) from the "editable track" (create / paste / save), so saving always writes the editable
  tier regardless of which track is focused.
- **MFA no longer stales the whole pipeline** (`fix/mfa-stale-and-editor-audio`): MFA denoises
  `allblocks.wav` **in place** (saving the pre-denoise audio as `allblocks_original.wav`), which made
  Mark-First-Stimuli and everything downstream go **stale** the moment MFA ran. Staleness now ignores
  `allblocks.wav` and tracks its sibling `block_wav_onsets.mat` instead (same concat step, untouched by
  MFA) — so an MFA run no longer stales the chain, but a genuine **re-concat** still does. Old manifests
  stay compatible (the recorded `allblocks.wav` fingerprint is dropped from the comparison).
- **Editor audio after MFA is configurable** (`fix/mfa-stale-and-editor-audio`): once MFA has run, the
  editor loads the **original** (pre-denoise) `allblocks_original.wav` by default; a new Settings → MFA
  checkbox (`editor_use_processed_audio`) switches it to the MFA-denoised audio.
- **Response-coding quick tags + inline rename** (`feat/rpcode-tags-inline-rename`): the editor's
  quick-tag palette is now **per task**, taken from the lab Wiki's error tables (`response_tags()` in
  `core/rpcode/errors.py`; Lexical Delay/No-Delay share the pp.9-10 set, each tag carrying its Wiki
  description as a tooltip). Clicking a quick tag now **replaces** the label name (it no longer appends
  `/CODE`). **Double-click a label** (or press **Enter**) to **edit its name in place** — an inline field
  over the chip that commits on Enter/blur and cancels on Esc (replacing the old rename dialog).
- **Robust errors + bundled word lists** (`feat/robust-errors-and-bundled-wordlists`): an uncaught
  exception in a Qt slot used to tear the whole app down. A global `sys.excepthook`
  (`gui/error_dialog.py`) now turns any unhandled error into a **non-fatal dialog with the traceback**,
  and a failing pipeline step pops the same dialog (the worker's error is surfaced, not just the red
  chip). The write-Trials step no longer demands manual configuration: it **defaults to the lab's
  bundled `word_lst.mat` / `nonword_lst.mat`** (vendored under `core/rpcode/wordlists/`, mirroring how
  MATLAB `load`ed them from the path); Settings still lets you point at your own (blank = bundled).
- **`Trials.mat` is now a struct array (parity)** (`fix/trials-struct-array`): write-Trials was saving
  a numpy `object` array of dicts, which scipy writes as a MATLAB **cell array of structs** — so our
  `Trials.mat` was a cell array (and larger, since every cell re-stores the field names) where the
  MATLAB pipeline produces a 1×N **struct array**. `save_trials` now builds a structured-dtype array
  → a real struct array. Also made `generate_trials` **idempotent** like the MATLAB: a re-run starts
  from the untouched `Trials_org.mat` backup instead of the previous output. (Re-run write-Trials on
  affected subjects to rewrite their `Trials.mat`.)
- **`.mat` files are now compressed (parity)** (`fix/trials-struct-array`): `save_mat` writes with
  `do_compression=True` to match MATLAB's default `save` (v7, zlib). scipy's uncompressed default made
  our `.mat` files ~20-40× larger than the MATLAB pipeline's (e.g. a 504-trial `Trials_org` was 359 KB
  vs MATLAB's ~18 KB; now ~10 KB). Lossless — `loadmat` decompresses transparently.

### Fixed (later)

- **Folders menu froze the UI** (`fix/folders-menu-freeze`): opening the 📂 Folders menu resolved
  the "Raw audio blocks" dir by walking the subject's Box folder tree (a bounded-depth `iterdir`
  walk) **on the GUI thread** in `aboutToShow` — slow on cloud storage (stat-ing/hydrating many
  placeholders), so the app hung. The walk now runs on a worker thread, cached per subject; the menu
  opens instantly and the blocks entry shows "(finding…)" until it resolves. The other shortcuts
  (results / D_Data / data root) were already cheap single `is_dir` checks.
- **MFA "Done" but empty — a swallowed per-patient failure** (`fix/mfa-per-patient-error`): the
  vendored MFA pipeline catches a per-patient error, prints `Errors occurred for the following
  patients`, and still **exits 0**. `_run_mfa` only checked the return code, so a failed subject was
  marked Done with no real alignment output. It now scans the log for that marker and raises (red
  chip + log tail) so the failure is visible. (Surfaced on Uniqueness Point D65, where a corrupted
  stim annotation file — `aelkahhaazh_words.txt` held phone rows — produced more stim entries than
  trials and crashed `annotateResp` mid-run.)
- **Editor showed the MFA-denoised audio with the option off** (`fix/mfa-macos-response-phase`):
  once MFA actually completed (above), `prepareForMFA` denoises `allblocks.wav` in place and backs
  up the pre-denoise audio as `allblocks_original.wav` — so a stale `editor_use_processed_audio:
  true` in the saved config finally took effect and the spectrogram showed the denoised signal. The
  editor's audio selection is hardened (`_editor_wav`: cloud-safe `exists`, clearer fallback) so with
  the option **off** it loads `allblocks_original.wav` (the raw signal), falling back to
  `allblocks.wav` only when MFA never denoised it.
- **MFA progress bar now actually moves** (`fix/mfa-macos-response-phase`): the pipeline's stdout was
  block-buffered when piped, so the GUI received nothing until the process exited — the bar sat
  indeterminate the whole run then snapped to full. `PYTHONUNBUFFERED=1` streams each line live; the
  phase map gained the aligner's stages (corpus setup → features → alignment → export → write
  labels); and the running step row shows a 1 Hz elapsed clock, so the long, output-less
  stimulus-loading phase (reading hundreds of annotation files from Box) visibly ticks instead of
  looking frozen.
- **MFA response-alignment phase failed on macOS/Linux** (`fix/mfa-macos-response-phase`): two more
  Windows-only assumptions in the vendored pipeline, found after the `stim_dir` fix let the run get
  further. (1) `run_resp` opened `merged_stim_times.txt.` with a **trailing dot** — Windows strips
  trailing dots from filenames so it found the real file, but on macOS/Linux the dot is significant,
  so `open()` raised `FileNotFoundError`, the response phase failed (caught → exit 0), and no
  `mfa_resp_words.txt` was produced. Patched in the vendored `mfa_pipeline.py` (documented in
  `mfa/VENDORED.md`, guarded by a test); verified on real D144 data (dotted → `FileNotFoundError`,
  dotless → 168 response windows). (2) The pipeline invokes the `mfa` aligner by **bare name**
  (`subprocess.run(['mfa', …])`), which needs the conda env's bin on PATH; launching the app without
  `conda activate` (desktop shortcut, IDE, bare `python` path) left it off PATH → `FileNotFoundError:
  'mfa'`. `run_mfa` now prepends the interpreter's bin dir (where `mfa` lives) to the subprocess
  PATH, so alignment runs regardless of how the app was launched.
- **Run log unreachable from the step's "done" chip** (`fix/mfa-macos-response-phase`): the state
  chip only emitted a click when it carried an error *detail*, so clicking a green **done** chip did
  nothing — there was no obvious way to see a completed step's log. The chip is now clickable
  whenever a run log exists (MFA); clicking it opens `mfa_run.log` plus any recorded error in the log
  viewer, and the row's meta line hints "click the chip for the run log".
- **MFA reported "done" but produced no labels** (`fix/mfa-stim-dir-and-run-visibility`): the
  vendored task configs hardcode a Windows `stim_dir` (`Box\CoganLab\…\stim_annotations`) that the
  pipeline joins onto `home_dir`. Off Windows the backslashes aren't path separators, and the Box
  mount isn't always literally `Box` (it's `Box-Box` on macOS) — so the join pointed nowhere, MFA
  found zero stim annotations, wrote an empty `mfa_stim_words.txt`, and died in `mergeAnnots` with
  "list index out of range". But the pipeline catches per-patient errors and **still exits 0**, so
  the step was recorded *done* with no labels written. Fixed by re-rooting the stim dir onto the
  real data root (`resolve_stim_dir`: normalises `\`/`/`, keeps the part after `CoganLab`, and
  passes it as a `task.stim_dir=` override) — verified against all four task configs and unchanged
  on Windows (same path the old join produced there). `_run_mfa` now also fails loudly on a silent
  miss — the subject appearing in the pipeline's "Errors occurred" list, or an empty
  `mfa_stim_words.txt` — and the dashboard no longer counts a 0-byte `mfa_stim_words.txt` as a
  completed MFA step.
- **Run-log visibility + quick folder access** (`fix/mfa-stim-dir-and-run-visibility`): MFA runs as
  a captured subprocess (no terminal window), so the failure above was invisible. The dashboard
  gained a bottom status bar — click it to open the last run log (`mfa_run.log`, scrolled to the
  error tail; falls back to the subject's recorded step errors) — plus a **📂 Open results folder**
  button that reveals the current subject's response-coding results folder in the OS file manager.
- **Undo corrupted a focused read-only lane** (`fix/editor-undo-and-tab-scroll`): undo/redo
  snapshotted and restored `_focus_lane` (whatever track Tab was on) instead of the one editable
  tier. Focusing a read-only track (e.g. cue) and pressing Ctrl+Z overwrote it with the editable
  tier's snapshot. Undo now always targets `_editable_lane` — the only tier that can change.
- **Tab navigation now overrides the playback auto-follow** (`fix/editor-undo-and-tab-scroll`):
  Tabbing to a label while playing scrolled the view to that label, but the next playhead tick
  immediately yanked it back. A Tab scroll now suspends the auto-follow until the playhead drifts
  back into the visible window (or playback is restarted).
- **App hard-crashed right after a step finished** (`fix/worker-callback-thread`): `run_in_thread`
  connected the `on_result`/`on_error`/`on_finished` callbacks to the worker's signals as bare
  closures. A signal connected to a plain callable (not a bound method of a main-thread `QObject`)
  gets a *direct* connection, so those callbacks ran on the **worker** thread — and the dashboard's
  post-step callback touches widgets (`_refresh_states`, `set_summary`), which is undefined
  behaviour off the GUI thread: a C++ abort the Python excepthook can't catch. Most visible on the
  final write-Trials step (its callback does the most UI work). Fixed by relaying every callback
  through a `_Dispatcher` `QObject` that lives in the parent's (GUI) thread, so the cross-thread
  delivery is queued onto that thread and the callbacks run there. (Other call sites already worked
  around this by only emitting signals from their callbacks; they're unaffected.)
- **Spectrogram worker crash:** `scipy.signal` was imported lazily inside the spectrogram builder,
  which runs on a worker thread — a first scipy import off the main thread is an access violation.
  It's now imported at module load (main thread).
- **MFA failed with a bare "exited with code 1"** (`fix/label-retime-and-mfa-dep`): the vendored
  pipeline imports `noisereduce` (it denoises each clip before alignment), but that dependency was
  missing from `environment.yml`, so the subprocess died at import — *before* Hydra ran — and the
  runner discarded the traceback, leaving only "RuntimeError: MFA exited with code 1". Added
  `noisereduce` to the env, and `_run_mfa` now writes the full pipeline output to
  `<results>/mfa_run.log` and includes the tail in the raised error so failures are diagnosable.

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
