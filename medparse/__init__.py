"""Medparse - structured medical PDF extraction pipeline."""

# Suppress sklearn version warnings from spaCy models
import warnings
warnings.filterwarnings(
    "ignore",
    message=".*Trying to unpickle.*version.*",
    category=UserWarning,
    module="sklearn",
)
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module="sklearn.base",
)

__all__ = ["__version__"]

__version__ = "1.1.0"  # IFU hardening: robust front-matter, whitespace restoration, strict filters
