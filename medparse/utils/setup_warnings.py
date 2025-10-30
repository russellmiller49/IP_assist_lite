"""Setup warnings configuration for medparse - call this early."""

import warnings
import os


def suppress_all_sklearn_version_warnings():
    """Comprehensive suppression of sklearn version warnings."""
    # Suppress all sklearn version mismatch warnings
    # These occur when spaCy models (trained with sklearn 1.1.2) are loaded
    # with sklearn 1.7.2, but they're safe to ignore
    
    warnings.filterwarnings(
        "ignore",
        message=".*Trying to unpickle.*version.*",
        category=UserWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message=".*InconsistentVersionWarning.*",
        category=UserWarning,
    )
    warnings.filterwarnings(
        "ignore",
        category=UserWarning,
        module="sklearn.base",
    )
    warnings.filterwarnings(
        "ignore",
        category=UserWarning,
        module="sklearn",
    )


# Set environment variable to suppress at module level
os.environ["SKLEARN_WARNINGS"] = "0"

# Apply immediately when imported
suppress_all_sklearn_version_warnings()

