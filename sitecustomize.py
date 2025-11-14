"""Force tempfile module to use repo-local writable directory."""

from __future__ import annotations

import os
import tempfile

_REPO_TMP = os.path.join(os.path.dirname(__file__), ".tmp")
os.makedirs(_REPO_TMP, exist_ok=True)

os.environ.setdefault("TMPDIR", _REPO_TMP)
os.environ.setdefault("TEMP", _REPO_TMP)
os.environ.setdefault("TMP", _REPO_TMP)

tempfile.tempdir = _REPO_TMP
