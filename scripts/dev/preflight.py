#!/usr/bin/env python3
"""Preflight checks for environment and dependencies.

This script verifies that the environment is correctly configured for Medparse,
checking for common issues like missing models, incompatible versions, etc.
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple

import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]


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


def check_emit_config() -> Tuple[bool, str]:
    """Ensure the shared emit configuration exists and declares required keys."""

    config_path = ROOT_DIR / "configs" / "_shared" / "emit.yaml"
    if not config_path.exists():
        return False, "configs/_shared/emit.yaml missing"

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return False, f"Failed to parse emit config: {exc}"

    emit_section = data.get("emit", data)
    required_keys = ["evidence_policy", "tables_mode", "max_relations"]
    missing = [key for key in required_keys if key not in emit_section]
    if missing:
        return False, f"emit config missing keys: {', '.join(missing)}"

    summary = ", ".join(f"{key}={emit_section[key]}" for key in required_keys if key in emit_section)
    return True, f"emit config ok ({summary})"


def check_doc_type_model() -> Tuple[bool, str]:
    """Verify doc-type model assets and sklearn version alignment."""

    manifest_path = ROOT_DIR / "models" / "doc_type" / "MANIFEST.json"
    model_path = manifest_path.with_name("model.joblib")

    if not manifest_path.exists():
        return False, "Doc-type MANIFEST.json missing (run scripts/train_doc_type.py)"

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"Failed to parse doc-type manifest: {exc}"

    declared_version = manifest.get("sklearn_version")
    try:
        from sklearn import __version__ as runtime_version
    except ImportError:
        return False, "scikit-learn not installed (required for doc-type model)"

    if not declared_version:
        return False, "Doc-type manifest missing sklearn_version"

    declared_major = declared_version.split(".")[:2]
    runtime_major = runtime_version.split(".")[:2]
    if declared_major != runtime_major:
        return False, f"Doc-type model targets sklearn {declared_version}, runtime is {runtime_version}"

    if not model_path.exists():
        return False, f"Doc-type model missing at {model_path}"

    labels = manifest.get("labels") or []
    return True, f"doc-type model ok (labels={len(labels)}; sklearn {declared_version})"


def run_preflight() -> int:
    """Run all preflight checks and return exit code."""
    checks: List[Tuple[str, Tuple[bool, str]]] = [
        ("Python Version", check_python_version()),
        ("spaCy", check_spacy()),
        ("typer", check_typer()),
        ("scikit-learn", check_sklearn_version()),
        ("scispacy", check_scispacy()),
        ("scispaCy Model", check_scispacy_model()),
        ("Emit Config", check_emit_config()),
        ("Doc-Type Model", check_doc_type_model()),
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
