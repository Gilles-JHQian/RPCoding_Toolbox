# RPCoding Toolbox

A local, cross-platform desktop app that runs the Cogan Lab **Response Coding** preprocessing
pipeline for ECoG speech-task data — replacing the legacy MATLAB + Audacity + MFA workflow with a
single guided tool. Automated steps batch across subjects; manual steps are done in a built-in,
Audacity-like waveform/spectrogram label editor. The Python ports faithfully reproduce the original
MATLAB outputs (golden-file verified).

Supported tasks: `LexicalDecRepNoDelay`, `LexicalDecRepDelay`, `Uniqueness_Point`.

**Docs:**
- [User Guide](docs/USER_GUIDE.md) — GUI workflow, settings, batch runs, the annotation editor, CLI.
- [Technical Documentation](docs/ARCHITECTURE.md) — architecture, data model, MATLAB ports, render
  engine, editor internals, threading model, testing.
- [Changelog](CHANGELOG.md) — what's been delivered, by milestone.

## Status

Early development; the end-to-end pipeline works (scan → automated steps + batch → annotation editor
for the manual steps → enriched `Trials.mat`). 148 tests pass. The GUI is built on **PySide6 +
pyqtgraph**; the core pipeline is a pure-Python library usable headless via a CLI. Remaining: the
deferred per-subject "irregular subjects" corrections (see the changelog).

## Setup

The project uses a single **conda** environment (bundling Montreal Forced Aligner so there is no
separate MFA env to configure).

```bash
# Create the environment (cross-platform)
conda env create -f environment.yml
conda activate rpcoding

# Download MFA models + install the custom lexical dictionary (one-time)
#   handled by scripts/setup_env.{sh,ps1}
```

On Windows with conda installed at a non-default location, invoke conda by full path, e.g.
`D:\conda\miniconda3\condabin\conda.bat env create -f environment.yml`.

## Development

```bash
ruff check . && black --check . && pytest
```

## License

See `LICENSE`.
