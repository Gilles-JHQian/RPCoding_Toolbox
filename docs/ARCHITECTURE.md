# RPCoding Toolbox — Technical Documentation

A local, cross-platform desktop app that runs the Cogan Lab **Response Coding** preprocessing
pipeline for ECoG speech-task data, replacing the legacy MATLAB + Audacity + MFA/Whisper workflow.
Automated steps batch across subjects; the two manual steps are done in a built-in Audacity-like
waveform/spectrogram label editor. The Python ports reproduce the original MATLAB outputs
(golden-file verified).

- **Stack:** Python 3.11, PySide6 (Qt) + pyqtgraph, NumPy/SciPy, soundfile, Montreal Forced Aligner.
- **Env:** a single conda environment (`environment.yml`) bundling MFA; see [User Guide](USER_GUIDE.md).
- **Tasks:** `LexicalDecRepNoDelay`, `LexicalDecRepDelay`, `Uniqueness_Point` (extensible).

---

## 1. Layered architecture

Three layers with a strict dependency rule, enforced by a CI guard test
([test_core_has_no_qt.py](../tests/test_core_has_no_qt.py)):

```
rpcoding.core   pure Python, ZERO Qt imports — the ported pipeline + data model. Unit-testable headless.
rpcoding.gui    PySide6 desktop app. Depends on core; core never depends on gui.
rpcoding.cli    thin headless entry point (scan / status / run / run-step / batch).
```

`core/mfa/pipeline/` is the lab's MFA pipeline **vendored verbatim** (excluded from ruff/black).

## 2. Repository layout

```
src/rpcoding/
  core/
    config.py            AppConfig (data root, MFA task map, word/nonword lists); JSON persistence
    paths.py             filesystem layout builders (pathlib, no drive letters)
    tasks.py             Task enum + task -> MFA-config map + Cogan_Task_Data folder names
    steps.py             pipeline Step DAG, StepKind, EffectiveState, per-step outputs
    session.py           SubjectSession: resolved paths, manifest, effective step states, summary()
    manifest.py          per-subject Manifest (step records, atomic JSON, fingerprints)
    scanner.py           scan D_Data/<task> for D<n>/S<n> subject folders
    runner.py            step actions (concat, trialinfo, events, MFA, write-Trials, denoise) + batch
    matio.py             scipy.io .mat load/save + MATLAB isfield "ladders"
    labels.py            Audacity tier (.txt) read/write — Interval, Tier
    trial_index.py       time -> trial lookup from cue/condition tiers
    wordlists.py         Word/Nonword classification from word_lst.mat / nonword_lst.mat
    audio/
      io.py concat.py    soundfile IO; combine_wavs port (block concat + onsets)
      render/            pyramid.py spectro.py cache.py colormap.py hashing.py (render engine)
    trialinfo/           merge.py build.py (combine/fix/cell2mat ports; D140 detector)
    events/              cue_events.py condition_events.py (make_*_events ports)
    rpcode/              rpcode2trials.py errors.py (bsliang_rpcode2trials port + taxonomy)
    mfa/                 runner.py models.py ingest.py + vendored pipeline/
  gui/
    app.py main_window.py dashboard.py            entry, window, dashboard
    settings_dialog.py batch_dialog.py progress_dialog.py
    editor_loader.py                              step -> (tiers, save path)
    config.py theme.py                            per-user config; palette + QSS
    widgets/             state_chip state_dot step_row subject_row subject_list
    editor/              track_container (AudioEditor) + lanes + interaction + workers
    workers/worker.py                             QThread helper
  cli/main.py
```

## 3. Data model & on-disk layout

`AppConfig.droot` is the CoganLab data root (`$BOX/CoganLab`). Everything is derived
([paths.py](../src/rpcoding/core/paths.py)):

| Tree | Path | Role |
|---|---|---|
| Raw acquisition | `ECoG_Task_Data/Cogan_Task_Data/<subj>/<task folder>/…` | per-block `*.wav` + `*_TrialData.mat` (read in by concat / build-trialinfo) — see the block-dir resolver below |
| Upstream | `D_Data/<task>/<subj>/**/mat/Trials.mat` | **required external input**; EDF timing; written back enriched |
| Results | `ECoG_Task_Data/response_coding/response_coding_results/<task>/<subj>/` | all pipeline artifacts |

Artifacts in the results dir: `allblocks.wav`, `block_wav_onsets.mat`, `trialInfo.mat`
(+ `trialInfo.report.json`), `first_stims.txt`, `cue_events.txt`, `condition_events.txt`,
`mfa/mfa_*.txt`, `bsliang_resp_words_errors.txt`, and a hidden `.rpcoding/` holding the
`manifest.json` and the regenerable render caches.

**Block-dir resolver** ([paths.py](../src/rpcoding/core/paths.py) `resolve_blocks_dir`): acquisition
naming was inconsistent — the task folder may be `Lexical` (not `Lexical No Delay`), the block files
may sit in a (possibly nested) timestamped *session* folder rather than `All Blocks`, and that folder
mixes practice files and hundreds of per-trial wavs with the block-level `*_Block_<n>_AllTrials.wav`.
The resolver narrows to the matching task-group folder under the subject, collects dirs holding
non-practice block `*_TrialData.mat`, scores them by a NoDelay/Delay keyword in the path, and picks
the best (most blocks). Block-wav discovery additionally skips per-trial (`*_Trial_<n>*`) and practice
files. Resolution is memoized on the session (the recursive scan can take seconds on cloud storage).

**Manifest** ([manifest.py](../src/rpcoding/core/manifest.py)): per-step record of
`state` (not_started | done | error), output/dep `fingerprint`s (`size:mtime_ns`), `ran_at`, and
`error`. Written atomically (temp + `os.replace`). `fingerprint()` swallows `OSError` so a Box
cloud-sync placeholder that can't be stat-ed (WinError 1006) reads as absent instead of crashing.

## 4. Pipeline steps & state machine

The fixed DAG ([steps.py](../src/rpcoding/core/steps.py)):

```
1 create_results   2 concat_wavs   3 build_trialinfo   4 denoise(optional)
5 mark_first_stims(manual)   6 make_events   7 run_mfa
8 response_coding(manual)    9 write_trials
```

**Effective state** ([session.py](../src/rpcoding/core/session.py) `effective_state`) combines the
on-disk artifacts with the manifest:

- A step is **Done** when its output exists on disk (`_completed_on_disk`), *even with no manifest* —
  so subjects already processed by the legacy MATLAB pipeline show green. File existence wins over a
  leftover error record; an **Error** is only shown when the artifact is absent.
- **Stale**: a recorded-done step whose tracked dependency fingerprints changed (e.g. `first_stims.txt`
  re-edited), or whose upstream is stale/missing.
- **Blocked**: an upstream step isn't done. **Needs-manual**: a manual step that's ready.
- `denoise` / `write_trials` have no detectable artifact, so they fall back to the manifest record.

`SubjectSession.summary()` returns `(done, total, representative_state)` for the subject list.

## 5. Ported MATLAB modules (faithful 1:1)

| MATLAB source | Python module | Semantics preserved |
|---|---|---|
| `combine_wavs.m` | [audio/concat.py](../src/rpcoding/core/audio/concat.py) | block order, 10 s zero pad, 1-based onset `len(big)+1`, equal-fs assert |
| `combine_trialInfo` / `fix_trialInfo_blocks` / `cell2mat_trials` | [trialinfo/merge.py](../src/rpcoding/core/trialinfo/merge.py) | highest-block selection; **D140** "missing earlier blocks" detect + concat/relabel/truncate |
| `make_cue_events_lr.m` | [events/cue_events.py](../src/rpcoding/core/events/cue_events.py) | per-block EDF anchor; `on = first_stim[b] + (Auditory − anchor)/30000`; 1.0 s dur; `<idx>_<sound>` |
| `make_condition_events.m` | [events/condition_events.py](../src/rpcoding/core/events/condition_events.py) | per-block cue anchor; 0.5 s dur; `<idx>_<cue>` (`:=:` / Yes/No / Repeat) |
| `bsliang_rpcode2trials.m` | [rpcode/rpcode2trials.py](../src/rpcoding/core/rpcode/rpcode2trials.py) | EDF realign `Diff = 30000·StimStart − Auditory`; NoDelay 3:1 invariant; Cue/Auditory/(Delay/Go)/Response tags; LATE/NOISY_BSL/EARLY/CORRECT |
| `bsliang_make_wordnonword_matrix.m` | [wordlists.py](../src/rpcoding/core/wordlists.py) | Word/Nonword by exact stim filename |
| `scantext.m` / `scanformat.m` | [labels.py](../src/rpcoding/core/labels.py) | tab-delimited `%f%f%s`, 6-decimal seconds, LF |

The `.mat` loader ([matio.py](../src/rpcoding/core/matio.py)) replicates every MATLAB `isfield`
ladder: stim `sound|stim`, cue `cue|condition`, audio onset
`audiostart|audioStart|stimulusAudioStart|stimuliAlignedTrigger|cueStart`. `simplify_cells=True`
collapses both cell-of-structs and struct-array `trialInfo` into a list of per-trial dicts.

**D140/D134 reconstruction:** each `*_TrialData.mat` holds `trialInfo` cumulative *within its run*;
split-run subjects chain cumulative run-end files to recover the full trial list (504 for D134/D140,
byte-exact vs the MATLAB output and verified against the lab's saved files).

## 6. Audio render engine (performance-critical)

Built once on load (worker threads), cached under `.rpcoding/cache/` keyed by a content hash:

- **Waveform** — a min/max LOD pyramid ([render/pyramid.py](../src/rpcoding/core/audio/render/pyramid.py)).
  On range change, the lane picks the level where samples/pixel ≈ 1, slices the visible window and
  draws a filled min/max envelope; cost is independent of zoom. Below level 0 it reads raw samples
  via soundfile and decimates on the fly.
- **Spectrogram** — STFT computed once to a **memory-mapped `.npy`** of dB magnitude
  ([render/spectro.py](../src/rpcoding/core/audio/render/spectro.py)); a single `pg.ImageItem` shows
  the visible slice, column max-pooled to the viewport width, with a Magma LUT + `HistogramLUTItem`
  (dB/contrast). Reslice is debounced ~40 ms.
- All lanes share **one X (time) axis** via `setXLink`; Y axes are hidden.

Real-data perf (50.9-min / 135 M-sample / 44.1 kHz `allblocks.wav`): ~6 s one-time build (cached
after), <15 ms reslice at any zoom.

## 7. The annotation editor

[editor/track_container.py](../src/rpcoding/gui/editor/track_container.py) (`AudioEditor`) stacks a
time ruler, waveform, spectrogram and N label lanes in a `GraphicsLayoutWidget`: col 0 = horizontal
track-name labels, col 1 = the plots (no left axis). It opens as a **separate top-level window**.
Both manual steps use one unified lane layout (first stim · condition · cue · response;
[editor_loader.py](../src/rpcoding/gui/editor_loader.py)), toggling only the editable lane. The
waveform amplitude auto-scales to a robust percentile of the per-bin peak (so click transients don't
flatten speech), and the spectrogram's default dB window is raised off the `p2/p98` percentiles for a
cleaner view. The toolbar selection readout is editable (type a precise start/end).

- **Label virtualization** ([editor/label_lane.py](../src/rpcoding/gui/editor/label_lane.py)):
  cue/condition/MFA tiers hold hundreds–thousands of intervals. The lane keeps intervals in a list
  and binds only a small recycled pool of region+text items to the labels *in view* (capped at 120,
  text only when sparse); pan/zoom rebinds the pool. A working window renders in ~2–15 ms instead of
  building thousands of items and freezing. The dense `*_phones` MFA tiers are excluded from the
  response-coding view ([editor_loader.py](../src/rpcoding/gui/editor_loader.py)).
- **Unified interaction** ([editor/interactive_viewbox.py](../src/rpcoding/gui/editor/interactive_viewbox.py)):
  every lane (ruler, waveform, spectrogram, label tracks) uses one `InteractiveViewBox`, so the
  gestures work over any track. **Left-drag** selects a time span (Audacity-style) → Ctrl+B creates
  a label on the editable tier; **Ctrl+wheel** zooms time about the cursor; **Shift+wheel** pans;
  plain wheel is a no-op. The gesture is applied to the shared (x-linked) axis.
- **Label selection:** clicking a label selects it (scene `sigMouseClicked` → the lane under the
  cursor → `select_at`). The selected label becomes draggable (body + endpoints; unselected labels
  stay non-movable so clicks reach the lane), **Enter** renames it, an error-palette code appends to
  it, **Delete** removes it, and its span highlights across all lanes.
- **Clipboard & undo/redo:** Ctrl+C/X/V copy/cut/paste a label (paste at the cursor/selection,
  preserving length); Ctrl+Z/Y undo/redo via a snapshot history of the editable tier (recorded on
  each `tier_changed`). The selection span is a movable `LinearRegionItem` (drag body = move, edge =
  resize) synced through the `SelectionModel`; dragging a label updates the highlight live via the
  region's `sigRegionChanged` (the `sigRegionChangeFinished` marks the tier dirty for save/undo).
- The selection span highlights across all lanes; the **Trial Info** panel maps the selection
  midpoint to its trial via the cue/condition tiers. **Open** is zoomed to the first 60 s (fast first
  render); **Fit** shows the whole file.
- **Save** writes the editable tier to its Audacity-compatible `.txt` and records the step done.

## 8. GUI dashboard

[dashboard.py](../src/rpcoding/gui/dashboard.py): task selector, subject list, per-step status, and
run controls. Per-step rows show a state dot + filled-pill chip + action button
([widgets/](../src/rpcoding/gui/widgets/)); the visual design follows the design handoff tokens
([theme.py](../src/rpcoding/gui/theme.py)). Behavior:

- Switching task auto-rescans; subject rows show file-based `done/total` from `summary()`, computed
  **one-per-event-loop-tick** via a `QTimer` so a large (cloud-synced) scan never blocks the UI.
- A single automated step runs **inline** (no popup), flipping its chip to *Running*; only batch runs
  open a dialog. **Errors** are re-runnable, hover the chip for the message, click for full detail.
- **Settings** edits the data root, word/nonword lists and the MFA task map; **Batch** runs the
  automated pipeline across the checked subjects with aggregated progress.

## 9. Concurrency model

Long ops (wav concat, trialInfo merge, MFA subprocess, rpcode2trials, pyramid/STFT builds) run off
the UI thread via [workers/worker.py](../src/rpcoding/gui/workers/worker.py) (`QObject` worker on a
`QThread`, kept alive in a module set until finished).

**UI-thread rule:** pyqtgraph / Qt graphics items must only be touched on the GUI thread. A worker's
`result` signal connected to a plain lambda is a *Direct* connection (runs on the worker thread), so
the render results are routed through editor signals (`_pyramid_ready` / `_spectro_ready`) whose slots
live on the editor (UI thread) → **queued** delivery there. (A direct off-thread `TextItem` create
after virtualization was an access violation that crashed the editor on open — fixed by this routing.)

## 10. MFA integration

The lab's pipeline is vendored under `core/mfa/pipeline/` and invoked with the current interpreter
(`sys.executable`) by [mfa/runner.py](../src/rpcoding/core/mfa/runner.py) (Hydra args, `cwd` = the
vendored dir). [mfa/models.py](../src/rpcoding/core/mfa/models.py) ensures the acoustic model +
dictionaries are present; [mfa/ingest.py](../src/rpcoding/core/mfa/ingest.py) parses `mfa_*.txt` into
tiers. The task→config map is configurable (`Uniqueness_Point` unmapped until supplied). MFA is one
step: if it errors the app stays usable (drop `mfa/*.txt` in and continue).

## 11. Testing & tooling

- **148 tests** (`pytest`). Core has golden/parity tests (cue/condition/Trials byte- or
  tolerance-exact vs real D134/D140 where the data is present, else `skipif`); GUI tests run offscreen
  (`QT_QPA_PLATFORM=offscreen`, `pytest-qt`) and are skipped where PySide6 is absent.
- **Guards:** `test_core_has_no_qt` (core imports no Qt); ruff + black (line-length 100), with the
  vendored MFA pipeline excluded.
- Run the gate: `ruff check . && black --check . && pytest`.

## 12. Environment & cross-OS

Single conda env from `environment.yml` (conda-forge), `pathlib` everywhere, no drive letters,
subprocess via `sys.executable`. The package is installed editable (`pip install -e . --no-deps`);
entry points: `rpcoding` (CLI), `rpcoding-gui` (app). On Windows, conda's `libsndfile.dll` is only on
PATH inside an **activated** env — launch via `conda activate rpcoding` (or `conda run`), not the env
python directly.

## 13. Known limitations / deferred

- **Irregular subjects** (`feat/irregular-subjects`, deferred): per-subject MATLAB corrections
  (D90/D28/D26/D92/D100/D102/D117/D23) and lenient count-mismatch recovery are not yet ported —
  the normal path raises a clear error on mismatch.
- `Uniqueness_Point` MFA config/dictionary is supplied by the user via the task map.
- `write_trials` completion isn't auto-detected from disk (no cheap marker); it relies on the manifest.
- Editor opens zoomed to the first 60 s for fast open; no audio playback yet.
