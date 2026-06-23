# Vendored: coganlab MFA_pipeline

The contents of `pipeline/` are vendored verbatim from the lab's local clone of the Montreal Forced
Aligner pipeline:

- Source: `coganlab/MFA_pipeline` (local clone at
  `…/Cogan lab/Response_Coding/MFA_pipeline`).
- Vendored: `mfa_pipeline.py`, `utils/` (`mfa_utils.py`, `stim_transcripts.py`, `delete_old_mfa.py`),
  `conf/` (Hydra config + per-task configs), `dictionary/` (`english_us_lr.dict` with nonwords, plus
  `english_us_ps`/`english_us_rc`), and the upstream `LICENSE` (MIT).

It is **run as a subprocess** (`python pipeline/mfa_pipeline.py patient_dir=… task=… patients=…`)
using the project's own Python (`sys.executable`), so `from utils import mfa_utils` and Hydra's
`config_path="conf"` resolve relative to the script. It is intentionally **not** a Python package
(no `__init__.py`) and is not imported by `rpcoding.core`.

To re-sync with upstream, re-copy the files above and update this note with the upstream commit.
Montreal Forced Aligner itself comes from the conda env (`environment.yml`); only the wrapper +
dictionaries are vendored.
