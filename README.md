# RPCoding Toolbox

A local, cross-platform desktop app that runs the Cogan Lab **Response Coding** preprocessing
pipeline for ECoG speech-task data — replacing the legacy MATLAB + Audacity + MFA workflow with a
single guided tool. Automated steps batch across subjects; manual steps are done in a built-in,
Audacity-like waveform/spectrogram label editor. The Python ports faithfully reproduce the original
MATLAB outputs (golden-file verified).

Supported tasks: `LexicalDecRepNoDelay`, `LexicalDecRepDelay`, `Uniqueness_Point`.

**Usage:** see the [User Guide](docs/USER_GUIDE.md) for the GUI workflow, settings, batch runs, the
annotation editor, and the headless CLI.

## Status

Early development. See the implementation plan and progress in the project notes. The GUI is built on
**PySide6 + pyqtgraph**; the core pipeline is a pure-Python library usable headless via a CLI.

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
