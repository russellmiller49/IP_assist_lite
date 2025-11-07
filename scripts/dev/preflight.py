#!/usr/bin/env python3
"""Preflight checks for environment and dependencies.

This script verifies that the environment is correctly configured for Medparse,
checking for common issues like missing models, incompatible versions, etc.
"""

import json
import sys
import warnings
from pathlib import Path
from typing import List, Tuple

import yaml

warnings.filterwarnings("ignore", message="Possible set union", module="spacy.language")

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
    label_set = set(labels)
    core_labels = {"guideline", "statement", "research", "ifu", "textbook"}
    missing_core = core_labels - label_set
    if missing_core:
        return False, f"Doc-type model labels missing: {', '.join(sorted(missing_core))}"
    optional = {
        "diagnostic_study",
        "therapeutic_trial",
        "practice_management",
        "research_therapeutic",
        "editorial_or_economics",
        "other_research",
    }
    missing_optional = sorted(optional - label_set)
    summary = f"doc-type model ok (labels={len(labels)}; sklearn {declared_version})"
    if missing_optional:
        summary += f" – optional labels missing {missing_optional}"
    return True, summary


def check_ifu_guard_config() -> Tuple[bool, str]:
    """Ensure IFU configuration declares guard and engine settings."""

    config_path = ROOT_DIR / "configs" / "run_ifu.yaml"
    if not config_path.exists():
        return False, "configs/run_ifu.yaml missing"

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return False, f"Failed to parse run_ifu.yaml: {exc}"

    ifu_block = data.get("ifu") or {}
    toc_guard = ifu_block.get("toc_guard")
    engine_block = ifu_block.get("engine") or {}
    threshold = ifu_block.get("small_ifu_threshold")

    missing = []
    if toc_guard is None:
        missing.append("toc_guard")
    if not engine_block or not all(key in engine_block for key in ("text", "tables")):
        missing.append("engine.text/tables")
    if threshold is None:
        missing.append("small_ifu_threshold")

    if missing:
        return False, f"IFU config missing {', '.join(missing)}"

    summary = (
        f"toc_guard_enabled={toc_guard.get('enabled', True)}; "
        f"engines=text={engine_block.get('text')},tables={engine_block.get('tables')}; "
        f"small_ifu_threshold={threshold}"
    )
    return True, summary


def check_ifu_resources() -> Tuple[bool, str]:
    """Validate supporting IFU resource files are present."""

    shared_dir = ROOT_DIR / "configs" / "_shared"
    frontmatter_path = shared_dir / "ifu_frontmatter.yaml"
    aliases_path = shared_dir / "ifu_section_aliases.yaml"

    missing: List[str] = []
    if not frontmatter_path.exists():
        missing.append(str(frontmatter_path))
    if not aliases_path.exists():
        missing.append(str(aliases_path))
    if missing:
        return False, f"Missing IFU shared config: {', '.join(missing)}"

    try:
        front_data = yaml.safe_load(frontmatter_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return False, f"Failed to parse {frontmatter_path.name}: {exc}"
    if not isinstance(front_data, dict):
        return False, f"Unexpected structure in {frontmatter_path.name}"

    pattern_bundle = front_data.get("pattern_bundle")
    if not isinstance(pattern_bundle, dict) or not pattern_bundle:
        return False, "IFU frontmatter pattern_bundle missing or empty"
    required_bundle_fields = {
        "manufacturers",
        "product_name",
        "part_number",
        "revision",
        "publication_date",
        "model",
    }
    missing_bundle = [field for field in required_bundle_fields if field not in pattern_bundle]
    if missing_bundle:
        return False, f"pattern_bundle missing keys: {', '.join(sorted(missing_bundle))}"

    try:
        alias_data = yaml.safe_load(aliases_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return False, f"Failed to parse {aliases_path.name}: {exc}"
    if not isinstance(alias_data, dict) or not alias_data:
        return False, "IFU section aliases missing entries"

    return True, "IFU resources available"


def check_second_pass_config() -> Tuple[bool, str]:
    config_path = ROOT_DIR / "configs" / "_shared" / "second_pass.yaml"
    if not config_path.exists():
        return False, "configs/_shared/second_pass.yaml missing"

    try:
        config_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return False, f"Failed to parse second_pass config: {exc}"
    shared_block = config_data.get("second_pass") if isinstance(config_data, dict) else None
    if shared_block is None:
        shared_block = config_data
    if not isinstance(shared_block, dict):
        return False, "second_pass config malformed"
    ifu_block = shared_block.get("ifu") if isinstance(shared_block, dict) else None
    if not isinstance(ifu_block, dict):
        return False, "second_pass.ifu block missing"
    density_cfg = ifu_block.get("safety_density_min")
    if not isinstance(density_cfg, dict):
        return False, "second_pass.ifu.safety_density_min missing"
    vendor_overrides = density_cfg.get("by_manufacturer")
    if isinstance(vendor_overrides, dict):
        vendor_summary = ", ".join(
            f"{name}:{value}" for name, value in vendor_overrides.items()
            if isinstance(name, str) and value is not None
        )
    else:
        vendor_summary = ""

    def _load_second_pass_mode(config_file: Path) -> str:
        if not config_file.exists():
            return "missing"
        try:
            data = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        except Exception:
            return "error"
        value = data.get("second_pass", "auto")
        return str(value)

    article_mode = _load_second_pass_mode(ROOT_DIR / "configs" / "run_article.yaml")
    ifu_mode = _load_second_pass_mode(ROOT_DIR / "configs" / "run_ifu.yaml")
    status = (article_mode.lower() == "auto" and ifu_mode.lower() == "auto")
    summary_bits = [f"article_second_pass={article_mode}", f"ifu_second_pass={ifu_mode}"]
    if vendor_summary:
        summary_bits.append(f"vendor_thresholds={vendor_summary}")
    message = "; ".join(summary_bits)
    return status, message


def check_ifu_frontmatter_config() -> Tuple[bool, str]:
    """Verify IFU front-matter regex bundle exists."""

    config_path = ROOT_DIR / "configs" / "_shared" / "ifu_frontmatter.yaml"
    if not config_path.exists():
        return False, "configs/_shared/ifu_frontmatter.yaml missing"
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return False, f"Failed to parse ifu_frontmatter.yaml: {exc}"

    manufacturers = data.get("manufacturers") or []
    bundle = data.get("pattern_bundle") or {}
    if not isinstance(manufacturers, list) or not manufacturers:
        return False, "ifu_frontmatter manufacturers block empty"
    if not isinstance(bundle, dict) or not bundle:
        return False, "ifu_frontmatter pattern_bundle missing"

    summary = f"manufacturers={len(manufacturers)}; bundle_keys={len(bundle)}"
    return True, summary


def check_article_topics() -> Tuple[bool, str]:
    """Validate presence of diagnostic topic config for ATS gating."""

    topics_path = ROOT_DIR / "configs" / "_shared" / "article_topics.yaml"
    if not topics_path.exists():
        return False, "configs/_shared/article_topics.yaml missing"
    try:
        data = yaml.safe_load(topics_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return False, f"Failed to parse article_topics.yaml: {exc}"
    if not isinstance(data, dict) or "diagnostic" not in data:
        return False, "article_topics.yaml missing 'diagnostic' block"
    return True, "article topics config ok"


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
        ("IFU Guard Config", check_ifu_guard_config()),
        ("IFU Resources", check_ifu_resources()),
        ("IFU Frontmatter Config", check_ifu_frontmatter_config()),
        ("Second-Pass Config", check_second_pass_config()),
        ("Article Topics", check_article_topics()),
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
