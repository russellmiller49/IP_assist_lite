#!/usr/bin/env python3
"""Preflight checks for environment and dependencies.

This script verifies that the environment is correctly configured for Medparse,
checking for common issues like missing models, incompatible versions, etc.
"""

import sys
from typing import List, Tuple


def check_python_version() -> Tuple[bool, str]:
    """Check Python version is 3.11+."""
    version = sys.version_info
    if version >= (3, 11):
        return True, f"Python {version.major}.{version.minor}.{version.micro}"
    return False, f"Python {version.major}.{version.minor} (requires >=3.11)"


def check_spacy() -> Tuple[bool, str]:
    """Check spaCy version."""
    try:
        import spacy

        version = spacy.__version__
        major, minor = map(int, version.split(".")[:2])

        if (major, minor) == (3, 7):
            return True, f"spaCy {version}"
        return False, f"spaCy {version} (requires 3.7.x)"
    except ImportError:
        return False, "spaCy not installed"
    except Exception as e:
        return False, f"spaCy error: {e}"


def check_typer() -> Tuple[bool, str]:
    """Check typer version (must be <0.10 for spaCy 3.7)."""
    try:
        import typer

        # typer doesn't expose __version__ directly, check via importlib
        from importlib.metadata import version

        ver = version("typer")
        major, minor = map(int, ver.split(".")[:2])

        if major == 0 and minor < 10:
            return True, f"typer {ver}"
        return False, f"typer {ver} (requires <0.10 for spaCy 3.7)"
    except ImportError:
        return False, "typer not installed"
    except Exception as e:
        return False, f"typer error: {e}"


def check_scispacy_model() -> Tuple[bool, str]:
    """Check if any scispaCy model is available."""
    try:
        import spacy

        models_to_try = ["en_core_sci_lg", "en_core_sci_md", "en_core_sci_sm"]
        available_models = []

        for model_name in models_to_try:
            try:
                nlp = spacy.load(model_name)
                version = nlp.meta.get("version", "unknown")
                available_models.append(f"{model_name} ({version})")
            except OSError:
                continue

        if available_models:
            return True, ", ".join(available_models)

        install_cmd = (
            "pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/"
            "releases/v0.5.4/en_core_sci_lg-0.5.4.tar.gz"
        )
        return False, f"No scispaCy models found. Install with:\n    {install_cmd}"
    except ImportError:
        return False, "spaCy not installed"
    except Exception as e:
        return False, f"Error checking models: {e}"


def check_sklearn_version() -> Tuple[bool, str]:
    """Check scikit-learn version."""
    try:
        from sklearn import __version__ as sklearn_version

        major, minor = map(int, sklearn_version.split(".")[:2])

        if major == 1 and 3 <= minor < 8:
            return True, f"scikit-learn {sklearn_version}"
        return False, f"scikit-learn {sklearn_version} (requires 1.3-1.7.x)"
    except ImportError:
        return False, "scikit-learn not installed"
    except Exception as e:
        return False, f"scikit-learn error: {e}"


def check_scispacy() -> Tuple[bool, str]:
    """Check scispacy version."""
    try:
        import scispacy

        version = scispacy.__version__
        if version == "0.5.4":
            return True, f"scispacy {version}"
        return False, f"scispacy {version} (recommends 0.5.4)"
    except ImportError:
        return False, "scispacy not installed (optional, needed for UMLS enrichment)"
    except Exception as e:
        return False, f"scispacy error: {e}"


def run_preflight() -> int:
    """Run all preflight checks and return exit code."""
    checks: List[Tuple[str, Tuple[bool, str]]] = [
        ("Python Version", check_python_version()),
        ("spaCy", check_spacy()),
        ("typer", check_typer()),
        ("scikit-learn", check_sklearn_version()),
        ("scispacy", check_scispacy()),
        ("scispaCy Model", check_scispacy_model()),
    ]

    print("=== Medparse Environment Preflight ===\n")

    all_pass = True
    for name, (passed, message) in checks:
        status = "✓" if passed else "✗"
        print(f"{status} {name:20} {message}")
        if not passed:
            all_pass = False

    print("\n" + ("=" * 40))

    if all_pass:
        print("All checks passed! Environment is ready.")
        return 0
    else:
        print("Some checks failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(run_preflight())
