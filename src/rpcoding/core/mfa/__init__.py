"""Vendored MFA pipeline integration: subprocess runner, model/dict setup, and output ingest.

The lab's MFA pipeline is vendored under ``pipeline/`` (run as a script, not imported) and invoked
with the current environment's Python (``sys.executable``) — the single conda env already provides
Montreal Forced Aligner, so there is no separate MFA environment to manage.
"""
