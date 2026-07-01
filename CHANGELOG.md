# Changelog

All notable changes to RPCoding Toolbox. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project is pre-release (`0.1.0`,
in development); entries are grouped by the feature branch that delivered them, newest first.

## [Unreleased]

### Response placeholders for MFA-dropped Repeat trials (`feat/response-omitted-placeholders`)

- **Write-Trials failed for UP subjects with "response count < Repeat count".** MFA writes one
  response window per Repeat trial, but where it fails to align one, `textGrid2txt` silently drops
  the empty-label row, so `mfa_resp_words` comes up short and the write-Trials 3:1 check (needs one
  response per Repeat trial) fires. (No Delay aligns cleanly so it rarely hits this; UP's
  pseudoword dictionary aligns less reliably — 6 subjects short by 1–8: D69/D94/D147/D63/D92/D130.)
- **Fix — one row per Repeat trial with placeholders** (`core/rpcode/response_fill.py`): the editor
  response lane now seeds a full tier — MFA-aligned responses mapped to their trial by cue-event
  time (so a window capped by `max_dur` never loses a real one), and for each un-aligned Repeat
  trial a placeholder: **`Omitted`** when the trial's `Omission == 'Responded'` (a real response
  exists — a coder must find and code it), else **`NOISY`** (the lab's no/unclear-response code, an
  acceptable final label). This also fixes the old positional mapping (a dropped row used to shift
  every later response).
- **Guard before writing Trials.mat:** `rpcode2trials.generate_trials` refuses to run while any
  response is still labelled `Omitted` ("还有 N 个 Omitted 没有检查 — review them in the editor").
  `NOISY` placeholders pass. Verified on the 6 subjects (all now reach 160 rows; Omitted counts
  match the `Omission=='Responded'` misses: D94=2, D130=1, others 0).

### Trigger-misalignment fix gadget (`feat/trigger-fix-algorithm`, `feat/trigger-fix-gui`)

- **The problem.** On some subjects (e.g. D90) `Trials.Auditory` is off by a *mis-counted trigger*:
  the manual `maketrigtimes` step dropped or double-counted a TTL pulse (a stray not zeroed, a missing
  pulse, or the double-trigger `trigTimes(1:2:end)` halving off by one), and because
  `ecog_preprocessing` consumes `trigTimes` with a single sequential cursor, one bad pulse shifts
  every later trial — a block-level **step** baked into `Trials.Auditory`, and from there into
  `cue_events`. This is distinct from the clock-drift fix: that corrects a smooth EDF-vs-audio *rate*
  drift on already-correct triggers; this repairs a trigger *count* error.
- **The idea.** The two ground truths survive the damage — the raw `trigger.mat` waveform (all real
  pulses still in it) and `trialInfo` (the experiment computer's authoritative per-trial timing). So
  re-detect the pulses and use trialInfo's stimulus-time pattern as a template to snap each trial back
  onto its own true pulse.
- **Algorithm (`core/trigger_fix.py`).** `detect_pulses` (adjustable threshold + noise-zeroing — the
  one genuinely per-subject step, mirroring `maketrigtimes`). `align_to_trialinfo` anchors once on the
  full-length template by **minimizing fit tightness** (tol-capped total distance), which locks onto
  the *stimulus* pulses rather than the *cue* pulses of the double trigger (both give a full template
  match, but cue pulses sit a variable ~2 s ahead of `stimulusAudioStart` so they fit loosely), then
  a **drift-tolerant sequential snap** re-anchors each trial and interpolates a missing pulse.
  `apply_trigger_fix` writes a corrected `Trials.mat` to the results dir and regenerates the
  cue/condition events; `is_improvement` guards the already-clean / irregular case so a clean file is
  never degraded. `resolve_trials_mat` now prefers a results-dir `Trials.mat` (the tool's own combine
  or a correction gadget's output) over the D_Data copy, so downstream steps read the corrected file.
- **Validated on real data.** D90 (broken block 1) `2281 ms → 7 ms` residual, aligned; D139 (already
  clean) reproduces the lab's answer (`18 ms → 4 ms`); D86 (irregular 851-pulse structure) is left
  untouched by the improvement guard.
- **UI (Settings → 异常处理 · Anomaly handling → 修复触发错位 · Fix trigger misalignment…).** Pick a
  task/subject, **Analyze** (loads the trigger once, then a threshold slider re-detects/re-aligns
  live), review the detected pulses + recovered trial grid over the max-pooled waveform and the
  before/after per-block residual, then **Apply**. (`gui/trigger_fix.TriggerFixDialog`.)

### Merge multi-part recordings (`feat/multipart-merge`)

- **Subjects recorded in more than one part** (e.g. No-Delay D147: `Trials1.mat` + `Trials2.mat`,
  `trialInfo1/2`, `experiment1/2`) never had a combined `Trials.mat`, so the pipeline couldn't run
  (`find_trials_mat` needs exactly one `**/mat/Trials.mat`). New `core/multipart.py` combines the
  numbered parts — **Trials / trialInfo concatenated in order** (matching the lab's
  `combine_trialInfo.m` horzcat; trial numbers and per-part timestamps left as-is), **experiment
  copied from part 1** (the parts are content-identical; copying also dodges scipy's 31-char
  field-name limit) — writing single `Trials.mat` / `trialInfo.mat` / `experiment.mat` next to their
  parts in D_Data. Existing merged files are never overwritten (idempotent). Exposed as **Settings →
  Anomaly handling → Merge multi-part files…**: pick a task/subject (defaults to the current one)
  and merge. Verified on D147 (252 + 252 → 504, experiment byte-identical to part 1).

### Clock-drift fix gadget (`feat/clock-fix-marking`, `feat/clock-fix-algorithm`)

- **The problem.** On early subjects the cue (stimulus) annotation slips progressively later through
  each block and resets at the block boundary: the EDF/amplifier clock (`Trials.Auditory`, 2048 Hz)
  drifts from the audio-interface clock (`allblocks.wav`, 20 kHz), and `cue_events` mixes the two
  (a `first_stims` audio anchor + EDF-elapsed). The lab already knew this
  (`bsliang_test_Auditoryonset_errors.m`: *"lags tended to gradually be bigger as time grows within
  a block"*, early patients <60 for No-Delay) and fixed it by hand-adjusting `cue_events`; this
  gadget automates it. (Verified from the EDF: `trigTimes_audioAligned − trigTimes` is a *constant*
  latency, so the trigger grid is accurate and only the EDF↔audio rate needs fixing.)
- **Marking (Settings → 异常处理 · Anomaly handling → 修复时钟差异 · Fix clock drift…).** Pick a
  task/subject; the editor opens `allblocks.wav` with an editable `clock_anchors` lane pre-seeded
  with one draggable anchor at each block's first and last trial (labelled by trial number, sitting
  at the drifted cue position). Drag each onto the true stimulus; add anchors on anomalous trials.
  Saved as `clock_anchors.txt`. (`gui/editor_loader.tiers_for_clock_anchors`,
  `gui/clock_fix.ClockFixDialog`; opens the editor in a step-less "clock-anchor" mode.)
- **Correction (`core/clock_fix.py`).** From the anchors + `Trials.Auditory`, each block's
  EDF-elapsed is re-mapped onto the true audio timeline by **piecewise-linear interpolation through
  the anchors** — exact with a start+end anchor, bending at extra (anomaly) anchors, so a non-linear
  block is handled. A block with <2 anchors is left unchanged. `cue_events` is rewritten onto the
  true positions; `condition_events` is shifted by each trial's same correction; originals are backed
  up once to `*.before_clock_fix.txt`. On save the editor offers to apply it and reports the
  per-block end-shift and rate (ppm). The neural-cutting times in the enriched `Trials.mat` stay
  EDF-anchored (`Trials.Auditory` + short per-trial intervals), so this correction is audio-domain
  only (coding + MFA windowing) and doesn't skew epoched neural data.

### Multi-session / multi-day subjects (`feat/multi-session-subjects`)

- **Blocks split across session folders + no combined `Trials.mat`.** A subject run across two EDF
  sessions/days splits its per-block TrialData/wavs over two timestamped session folders (e.g.
  No-Delay **D133**: blocks 1-2 in one, 3-4 in another) and has only per-session
  `Trials1.mat`/`Trials2.mat`. `resolve_blocks_dir` returned a single folder, so trialInfo build +
  wav concat only saw one session. New **`paths.resolve_block_dirs`** returns *all* the task's
  session folders; `discover_trialdata_files` / `discover_block_wavs` now aggregate across them (a
  block present in two sessions resolves to the most-complete / latest run). **`core/trials_combine.py`**
  (`resolve_trials_mat`) uses an existing combined `Trials.mat`, else **auto-combines the per-session
  `Trials<N>.mat`** — renumbering `Trial` to a continuous 1..N (byte-matches the lab's hand-combined
  D133) — into the *results* dir (never the shared D_Data). The runner's event/write steps use this
  tolerant lookup (also fixing a latent `find_trials_mat` WinError-1006 crash on Box placeholders),
  and a ⚠ advisory (run log + status bar, persisted in the manifest) fires whenever a combine
  happens. Verified end-to-end: D147 (never hand-combined → 504 trials, 13 ms aligned) and D133.
  (Complements the manual `feat/multipart-merge` button, which pre-writes a combined `Trials.mat`
  into D_Data; `resolve_trials_mat` then just uses it.)
- **Uniqueness-Point Trials.mat health checks.** Two read-only diagnostics (never touch the dataset):
  `scripts/up_trials_healthcheck.py` (self-contained geometry check per downloaded `Trials.mat` —
  length, monotonic `Auditory`, `Start→Auditory` interval, block-boundary alignment vs 120/240/360)
  and `scripts/up_trialinfo_xcheck.py` (the authoritative §2.6 cross-check — per-trial
  `Trials.Auditory` vs `trialInfo.stimulusAudioStart`, pinpointing the exact trial where a block goes
  off). Flagged D86/D90/D84/D139/D121 as misaligned (D139 only via the trialInfo cross-check).

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

### App launcher, icon & title (`feat/launcher-and-icon`)

- **Double-click launchers** in the project root, cross-platform: `launch.bat` (Windows, console-less)
  and `launch.command` (macOS Finder / Linux). Each finds the `rpcoding` conda env automatically.
  Command-line launch is unchanged (`rpcoding-gui` or `python -m rpcoding.gui.app`). `.gitattributes`
  pins `.bat`→CRLF and `.command`/`.sh`→LF so the shebang isn't broken on macOS.
- **Brain icon.** A simple cute-brain icon (`rpcoding/gui/assets/brain.{png,ico}`, generated by
  `scripts/make_brain_icon.py`) is now the window + taskbar icon (an explicit Windows AppUserModelID
  makes the taskbar use it rather than python's).
- **Window title** is now **"Cogan Lab RP Coding Toolbox"**.

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

### Editor — type a playback multiplier past 10× (`feat/volume-manual-input`)

- The playback-volume control gained an **editable multiplier box** beside the slider. The slider
  still gives fine 0–10× control, but very quiet recordings can now be boosted by typing a value up
  to 100× (playback clips at ±1, so it just gets loud). Typing a value >10× applies it and parks the
  slider at its 10× max; nudging the slider then takes over again within 0–10×.

### Word/Nonword lists — Uniqueness Point integration (`feat/wordlists-uniqueness-point`)

- **The default Word/Nonword lists now cover Uniqueness Point, not just Lexical.** `rpcode2trials`
  tags each trial Word/Nonword by matching its stimulus filename against these lists; UP stimuli
  (`altitude.wav` / `ahlawjahns.wav` …) matched neither, so UP write-Trials would mis-tag every
  trial. The bundled `word_lst.mat` / `nonword_lst.mat` are now the **union** of the lab's Lexical
  lists (84 + 84) and the UP set (40 words + 40 nonwords) — 124 + 124 entries, the two being
  disjoint. The UP stimulus metadata is vendored
  (`core/rpcode/wordlists/uniqueness_point_stimuli.csv`) and the lists are rebuilt by the idempotent
  `scripts/build_wordlists.py`. Verified: every trial of D90/D147/D86 now classifies.

### Batch run — stop at manual gates + a Stop button (`feat/batch-stop-and-manual-gate`)

- **Batch stops at the manual gate instead of running past it.** `run_pipeline` now steps *past* a
  manual step only when it's already done, and otherwise **stops the pass** there — so a batch runs
  the prep up to response coding and halts, instead of skipping the manual step and writing Trials.
- **Batch never auto-writes Trials.mat.** The terminal write-back enriches `D_Data/**/Trials.mat` in
  the shared Box dataset — a deliberate, per-subject action. `run_batch` now excludes
  `WRITE_TRIALS` (new `BATCH_ACTIONS`); previously, when response coding merely *looked* done (its
  output file present) batch would re-write Trials to Box on every run, because `WRITE_TRIALS` has no
  results-dir output to mark it done. Write Trials per subject from the dashboard when ready.
- **Stop button.** The batch dialog gained a **Stop** that cooperatively cancels: `run_batch` /
  `run_pipeline` poll a `should_cancel` callback before each subject and before each step, so the run
  winds down cleanly (the in-flight step — e.g. an MFA alignment — finishes first). Closing the
  dialog mid-run also cancels; remaining subjects are marked "— stopped".

### Editor — block-onset navigation track (`feat/block-onset-track`)

- **A read-only "block" lane** at the top of the annotation editor marks where each block begins in
  the concatenated `allblocks.wav` (labels `block 1`…`block N`). When marking each block's first
  stimulus you can jump straight to a block's start (click the marker, or focus the lane and Tab
  between blocks) instead of hunting through ~27 min of audio. Derived on the fly from
  `block_wav_onsets.mat` — no extra artifact, works for any already-concatenated subject — via
  `core/events/block_onsets.py` (onset = `(start_sample - 1) / fs`; missing block rows skipped).
  Shown on the mark-first-stims, response-coding, and denoise editors.

### Fixed (later)

- **Response palette "LATR_RESP" → "LATE_RESP" typo** (`fix/latr-resp-typo`): the editor's late-
  response quick-tag read `LATR_RESP`, but the tag rpcode2trials actually writes (and that MATLAB
  `bsliang_rpcode2trials.m` derives) is `LATE_RESP`. The palette code is never consumed by the
  pipeline, so no data was affected — but the spelling now matches the canonical derived tag.
- **Spectrogram was drawn ~17 ms too early** (`fix/spectrogram-time-alignment`): the spectrogram
  sat slightly left of the waveform, so a stop burst / high-energy peak appeared *before* the
  envelope showed it. `scipy.signal.stft(boundary=None)` centres frame `c` on sample
  `c*hop + n_fft/2`, but each column was placed at `c*dt` (its window's *start*), shifting the whole
  image earlier by `(n_fft - hop) / (2*fs)` — 17.4 ms at the recordings' 44.1 kHz. `slice_spectro`
  now applies that `frame_time_offset` so columns land under the matching waveform sample; the
  offset is stored in the cache meta (older caches recompute it — no rebuild needed). The waveform
  was already sample-accurate.
- **Corrected first_stims marked against the early spectrogram** (`fix/first-stims-offset`): onsets
  placed by eye against the (then ~17 ms-early) spectrogram inherited that offset, so they sat
  early. `core/first_stims_offset.py` shifts a subject's `first_stims.txt` onsets *later* by
  `frame_time_offset(fs)`, keeping a backup (`first_stims.before_offset_fix.txt`) and an idempotency
  marker (`.rpcoding/first_stims_offset.json`); `restore_first_stims` undoes it. `scripts/
  fix_first_stims_offset.py` applied it to the 27 subjects marked with the app this session — the
  offset computed **per subject from its own `allblocks.wav` fs**: +17.41 ms at 44.1 kHz, and
  **+38.40 ms for the four 20 kHz recordings (D28/D29/D42/D54)** (a flat 17.4 ms would have
  under-corrected those). Downstream cue/condition events inherit the shift — regenerate events to
  propagate it.
- **Errored step could still show "Done"** (`fix/pipeline-status-trials-box-retry`): when a step
  failed but an output file already existed, the dashboard showed Done because file-presence
  overrode the recorded error — e.g. re-running *Generate cue + condition events* (step 6), which
  errors early on the `Trials.mat` lookup while the prior run's `cue_events.txt` lingers, or
  *Write Trials* (step 9), whose output doubles as its input and so always "exists". A recorded
  error from the most recent run is now authoritative: the step shows red regardless of leftover
  artifacts, and a subsequent successful re-run clears it. (Reverses the earlier "disk presence wins
  over a leftover error record" rule for **our own** runs; legacy subjects with no manifest still go
  green from file presence.)
- **Auto-retry transient Box read/write errors** (`fix/pipeline-status-trials-box-retry`): Box
  intermittently fails a file read mid-sync (WinError 1006 "the volume for a file has been changed",
  or a brief lock), which surfaced as a spurious step failure — most often on *Generate cue +
  condition events*. `run_step` now wraps each automated step in `core/retry.py`, which waits ~0.6 s
  and retries (up to 4×) on a transient `OSError`; a genuinely missing file (`FileNotFoundError`) is
  never retried. The running step's progress line shows "Cloud storage hiccup; waiting then
  retrying…".
- **Duplicate `Trials.mat` no longer hard-errors** (`fix/pipeline-status-trials-box-retry`): some
  D_Data subjects carry both the canonical `<subject>/<date>/mat/Trials.mat` (where
  `ecog_preprocessing.m` writes) **and** a stray copy directly under `<subject>/mat/`.
  `find_trials_mat` raised "Found more than one Trials.mat"; it now prefers the canonical
  date-folder copy and logs the ignored duplicate, only erroring when the matches are genuinely
  ambiguous (e.g. two different date folders). (Seen on Uniqueness Point D94.)
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
