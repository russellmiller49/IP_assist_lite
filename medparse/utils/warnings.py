"""Configure warnings for medparse."""

import warnings


def suppress_sklearn_version_warnings():
    """Suppress sklearn version mismatch warnings when loading models."""
    # Suppress InconsistentVersionWarning from sklearn
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
    warnings.filterwarnings(
        "ignore",
        message=".*InconsistentVersionWarning.*",
    )


def configure_warnings():
    """Configure all medparse warnings."""
    suppress_sklearn_version_warnings()

