"""Enforce the layer DAG via a static import audit.

Rules (see docs/business_plan.md implementation plan §1 layer table):

| Layer          | May import from                                            | May NOT import from       |
|----------------|------------------------------------------------------------|---------------------------|
| routes/        | services/, models/, errors/, security/                     | db/, repositories/        |
| services/      | repositories/, models/, errors/, security/, extraction_* | routes/, db/entities      |
| repositories/  | db/, errors/                                               | routes/, services/, models/ |
| db/            | — (nothing upstream)                                       | everything                |
| models/        | stdlib, pydantic                                           | all of the above          |

This test greps for forbidden ``from business_layer.<x>`` imports in
files under each layer. A real import-graph library would be nicer,
but this is 30 lines, zero deps, and impossible to cheat without
getting caught in PR review.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent  # business_layer/
_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+business_layer\.([a-zA-Z0-9_]+)",
    re.MULTILINE,
)

# Per-layer denylists of *top-level* sub-packages. Files in the key
# layer MUST NOT import any of the listed sub-packages.
_FORBIDDEN: dict[str, set[str]] = {
    "routes": {"db", "repositories"},
    "services": {"routes"},
    "repositories": {"routes", "services", "models"},
    "db": {"routes", "services", "repositories", "models", "security"},
    "models": {"routes", "services", "repositories", "db", "security", "workers", "errors"},
}


# Files exempt from the layer rule — documented seams between layers.
#
# `routes/deps.py` is the FastAPI DI factory: by design it composes
# `db.get_session` + repo dataclass types into `Depends()` callables
# that the ACTUAL route handlers consume. The route handlers
# themselves (every other file under routes/) must not cross the
# layer boundary — the test catches THAT.
_EXEMPT = {
    ("routes", "deps.py"),
}


def _py_files(layer: str) -> list[Path]:
    layer_dir = _ROOT / layer
    if not layer_dir.exists():
        return []
    out: list[Path] = []
    for p in layer_dir.rglob("*.py"):
        if p.name == "__init__.py":
            continue
        rel = p.relative_to(_ROOT)
        parts = rel.parts
        # Skip exempt files keyed by (layer, filename).
        if (parts[0], parts[-1]) in _EXEMPT:
            continue
        out.append(p)
    return out


@pytest.mark.parametrize("layer,forbidden_subpkgs", sorted(_FORBIDDEN.items()))
def test_layer_imports(layer: str, forbidden_subpkgs: set[str]) -> None:
    """Every .py file in ``<layer>/`` must not import any forbidden subpkg.

    Empty layers (no .py files yet) pass trivially — Sprint 0 has
    several scaffolded-but-empty layers and that's OK.
    """
    offenders: list[tuple[str, str]] = []
    for path in _py_files(layer):
        text = path.read_text(encoding="utf-8")
        for match in _IMPORT_RE.finditer(text):
            subpkg = match.group(1)
            if subpkg in forbidden_subpkgs:
                offenders.append((str(path.relative_to(_ROOT)), subpkg))
    assert not offenders, (
        f"Layer rule violation — {layer}/ may not import "
        f"business_layer.{{{', '.join(sorted(forbidden_subpkgs))}}}: {offenders}"
    )
