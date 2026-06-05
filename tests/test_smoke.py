"""Phase 0 smoke test — verify the package imports cleanly."""
from __future__ import annotations


def test_package_imports() -> None:
    import app  # noqa: F401

    assert app.__version__
