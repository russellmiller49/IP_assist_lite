#!/usr/bin/env python3
"""
Doctor script for IP Assist Lite - Health checks for the environment.

Run this script to verify:
- Python and package versions
- medparse import path
- spaCy model availability
- scikit-learn version consistency
- Package conflicts

Usage:
    python scripts/doctor.py
"""

import sys
import pkgutil
import warnings
from pathlib import Path
from typing import Optional

# Suppress warnings during import
warnings.filterwarnings('ignore')


def check_python_version():
    """Check Python version."""
    print("=" * 60)
    print("Python Version Check")
    print("=" * 60)
    print(f"Python: {sys.version}")
    print(f"Executable: {sys.executable}")
    print(f"site-packages: {sys.prefix}")
    print()


def check_medparse_import():
    """Check where medparse is imported from."""
    print("=" * 60)
    print("Medparse Import Check")
    print("=" * 60)
    try:
        import medparse
        import inspect
        
        src_file = inspect.getsourcefile(medparse)
        file_path = src_file or medparse.__file__
        
        if file_path:
            abs_path = Path(file_path).resolve()
            print(f"✓ medparse imported from: {abs_path}")
            
            # Check if it's from workspace
            workspace_root = Path(__file__).resolve().parent.parent
            if workspace_root in abs_path.parents:
                print(f"✓ medparse is from workspace: {workspace_root}")
            else:
                print(f"⚠ medparse is NOT from workspace (expected in {workspace_root})")
        else:
            print(f"⚠ Could not determine medparse file location")
            
        try:
            version = medparse.__version__
            print(f"✓ medparse version: {version}")
        except AttributeError:
            print(f"⚠ medparse.__version__ not found")
            
    except ImportError as e:
        print(f"✗ medparse import failed: {e}")
        
    # Check for multiple medparse installations
    found_modules = list(pkgutil.iter_modules())
    medparse_modules = [m.name for m in found_modules if 'medparse' in m.name.lower()]
    if medparse_modules:
        print(f"Medparse-related modules found: {medparse_modules}")
    print()


def check_spacy_model():
    """Check spaCy and en_core_sci_lg model."""
    print("=" * 60)
    print("SpaCy & Model Check")
    print("=" * 60)
    try:
        import spacy
        print(f"✓ spacy version: {spacy.__version__}")
        
        try:
            nlp = spacy.load("en_core_sci_lg")
            print(f"✓ en_core_sci_lg model loaded")
            print(f"  Model name: {nlp.meta.get('name')}")
            print(f"  Model version: {nlp.meta.get('version')}")
        except OSError as e:
            print(f"✗ en_core_sci_lg model not found: {e}")
            print("  Install with: pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz")
        except Exception as e:
            print(f"✗ Failed to load model: {e}")
            
    except ImportError as e:
        print(f"✗ spacy import failed: {e}")
    print()


def check_sklearn_version():
    """Check scikit-learn version."""
    print("=" * 60)
    print("Scikit-learn Version Check")
    print("=" * 60)
    try:
        import sklearn
        print(f"✓ scikit-learn version: {sklearn.__version__}")
        
        # Check for version consistency
        expected_version = "1.1.2"
        actual_version = sklearn.__version__
        
        if actual_version == expected_version:
            print(f"✓ Version matches expected: {expected_version}")
        else:
            print(f"⚠ Version mismatch:")
            print(f"   Expected: {expected_version}")
            print(f"   Actual: {actual_version}")
            print(f"   This may cause pickle warnings if models were trained with different version")
            
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            print("✓ TfidfVectorizer available")
        except ImportError as e:
            print(f"✗ TfidfVectorizer import failed: {e}")
            
    except ImportError as e:
        print(f"✗ scikit-learn import failed: {e}")
    print()


def check_key_packages():
    """Check key package versions."""
    print("=" * 60)
    print("Key Package Versions")
    print("=" * 60)
    
    packages = [
        ("torch", "torch"),
        ("typer", "typer"),
        ("pandas", "pandas"),
        ("numpy", "numpy"),
        ("PyMuPDF", "fitz"),
        ("pdfplumber", "pdfplumber"),
        ("spacy", "spacy"),
        ("scispacy", "scispacy"),
        ("joblib", "joblib"),
    ]
    
    for pkg_name, import_name in packages:
        try:
            module = __import__(import_name)
            version = getattr(module, "__version__", "unknown")
            print(f"✓ {pkg_name}: {version}")
        except ImportError:
            print(f"✗ {pkg_name}: not installed")
        except Exception as e:
            print(f"⚠ {pkg_name}: {e}")
    print()


def check_package_conflicts():
    """Check for package conflicts using pip check."""
    print("=" * 60)
    print("Package Conflicts Check")
    print("=" * 60)
    
    import subprocess
    try:
        result = subprocess.run(
            ["pip", "check"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✓ No package conflicts detected")
        else:
            print("⚠ Package conflicts found:")
            print(result.stdout)
            print(result.stderr)
    except Exception as e:
        print(f"⚠ Could not run pip check: {e}")
    print()


def check_environment_variables():
    """Check relevant environment variables."""
    print("=" * 60)
    print("Environment Variables")
    print("=" * 60)
    
    import os
    
    vars_to_check = [
        "MEDPARSE_PROFILE",
        "MEDPARSE_UMLS_MODEL",
        "MEDPARSE_DISABLE_GPU",
        "PYTHONUTF8",
        "CUDA_VISIBLE_DEVICES",
    ]
    
    for var in vars_to_check:
        value = os.environ.get(var, "not set")
        print(f"{var}: {value}")
    print()


def main():
    """Run all health checks."""
    print("\n" + "=" * 60)
    print("IP Assist Lite - Environment Health Check")
    print("=" * 60)
    print()
    
    check_python_version()
    check_medparse_import()
    check_spacy_model()
    check_sklearn_version()
    check_key_packages()
    check_package_conflicts()
    check_environment_variables()
    
    print("=" * 60)
    print("Health check complete")
    print("=" * 60)
    print()
    print("If you see warnings, check the setup guide:")
    print("  scripts/setup_environments.sh")
    print()


if __name__ == "__main__":
    main()

