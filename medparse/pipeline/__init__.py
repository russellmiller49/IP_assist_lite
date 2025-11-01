"""Pipeline orchestration utilities with lazy imports to avoid cycles."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["PipelineOutcome", "run_extract"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        module = import_module("medparse.pipeline.run_extract")
        return getattr(module, name)
    raise AttributeError(name)
