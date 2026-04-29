"""Single source of truth for build/version info.

Exposed in the startup log line and on ``GET /health`` so that any
production incident can be tied back to a specific build.

* ``version`` — the SemVer string from ``pyproject.toml``. We read it at
  module import (cheap, one disk read) so the runtime never drifts from
  the canonical declaration.
* ``git_sha`` — short commit hash of the running build. Sources, in
  order of preference:
    1. ``RENDER_GIT_COMMIT`` env var (Render injects this automatically).
    2. ``GIT_SHA`` env var (set explicitly by Dockerfile or ops scripts).
    3. ``"dev"`` fallback for local development.

The fallback is intentional — falling back to "dev" loudly identifies
"this isn't a deployed build" in any log, rather than failing at import
time and breaking a fresh clone.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def get_version() -> str:
    """Return the SemVer string declared in ``pyproject.toml``.

    Falls back to ``"0.0.0+unknown"`` if pyproject.toml is missing or
    malformed (shouldn't happen in a real install — Hatchling ensures
    the file is present — but the fallback prevents an import-time
    crash from masking the real issue).
    """
    pyproject = _REPO_ROOT / "pyproject.toml"
    if not pyproject.exists():
        return "0.0.0+unknown"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return "0.0.0+unknown"
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        return "0.0.0+unknown"
    return m.group(1)


def get_git_sha() -> str:
    """Return the short git SHA of the current build, or ``"dev"``.

    Not lru_cached — it's an env-var read, faster than the cache lookup.
    """
    return (os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_SHA") or "dev")[:12]
