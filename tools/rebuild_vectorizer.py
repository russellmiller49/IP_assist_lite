#!/usr/bin/env python3
"""
Retrain vectorizer models under a new scikit-learn version.

Use this when you need to migrate from scikit-learn 1.1.2 to 1.7.2 or later.

This script:
1. Loads your training corpus
2. Retrains TfidfVectorizer under the current sklearn version
3. Saves the model with a version-specific filename
4. Updates the loader to use the new model

Usage:
    # First, upgrade sklearn to target version
    pip install "scikit-learn==1.7.2"
    
    # Run the rebuild script
    python tools/rebuild_vectorizer.py --corpus-dir training/articles --output models/tfidf_vectorizer_skl_1_7_2.joblib
"""

import argparse
import sys
from pathlib import Path
from typing import List

import joblib
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer


def get_sklearn_version():
    """Get current sklearn version."""
    return sklearn.__version__


def load_corpus(corpus_dir: Path) -> List[str]:
    """Load training documents from directory."""
    docs = []
    
    if not corpus_dir.exists():
        print(f"✗ Corpus directory not found: {corpus_dir}")
        return docs
    
    # Look for .txt files
    txt_files = list(corpus_dir.glob("*.txt"))
    
    for txt_file in txt_files:
        try:
            content = txt_file.read_text(errors="ignore")
            if content.strip():
                docs.append(content)
        except Exception as e:
            print(f"⚠ Failed to read {txt_file}: {e}")
    
    return docs


def train_vectorizer(
    corpus: List[str],
    min_df: int = 3,
    ngram_range: tuple = (1, 2),
    max_features: int = 200000,
) -> TfidfVectorizer:
    """Train a new TfidfVectorizer on the corpus."""
    print("Training TfidfVectorizer...")
    print(f"  min_df: {min_df}")
    print(f"  ngram_range: {ngram_range}")
    print(f"  max_features: {max_features}")
    
    vectorizer = TfidfVectorizer(
        min_df=min_df,
        ngram_range=ngram_range,
        max_features=max_features,
    )
    
    vectorizer.fit(corpus)
    
    print(f"✓ Vocabulary size: {len(vectorizer.vocabulary_)}")
    return vectorizer


def main():
    parser = argparse.ArgumentParser(
        description="Retrain vectorizer models under new sklearn version"
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path("training/articles"),
        help="Directory containing training .txt files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for the model (default: models/tfidf_vectorizer_skl_{version}.joblib)",
    )
    parser.add_argument(
        "--min-df",
        type=int,
        default=3,
        help="Minimum document frequency (default: 3)",
    )
    parser.add_argument(
        "--max-features",
        type=int,
        default=200000,
        help="Maximum number of features (default: 200000)",
    )
    parser.add_argument(
        "--ngram-range",
        type=str,
        default="1,2",
        help="N-gram range as comma-separated (default: 1,2)",
    )
    
    args = parser.parse_args()
    
    # Get sklearn version
    skl_version = get_sklearn_version()
    print(f"Current scikit-learn version: {skl_version}")
    
    # Determine output path
    if args.output is None:
        version_str = skl_version.replace(".", "_")
        args.output = Path("models") / f"tfidf_vectorizer_skl_{version_str}.joblib"
    
    # Ensure output directory exists
    args.output.parent.mkdir(parents=True, exist_ok=True)
    
    # Load corpus
    print(f"\nLoading corpus from: {args.corpus_dir}")
    corpus = load_corpus(args.corpus_dir)
    
    if not corpus:
        print("✗ No documents found in corpus")
        print("Expected .txt files in the corpus directory")
        sys.exit(1)
    
    print(f"✓ Loaded {len(corpus)} documents")
    
    # Parse ngram range
    ngram_parts = args.ngram_range.split(",")
    ngram_range = (int(ngram_parts[0]), int(ngram_parts[1]))
    
    # Train vectorizer
    vectorizer = train_vectorizer(
        corpus,
        min_df=args.min_df,
        ngram_range=ngram_range,
        max_features=args.max_features,
    )
    
    # Save model
    print(f"\nSaving model to: {args.output}")
    joblib.dump(vectorizer, args.output, compress=3)
    
    print(f"✓ Model saved successfully")
    print(f"  Output: {args.output}")
    print(f"  sklearn version: {skl_version}")
    
    # Provide next steps
    print("\n" + "=" * 60)
    print("Next steps:")
    print("=" * 60)
    print("1. Update your model loader to use this new model:")
    print(f'   vec = joblib.load("{args.output}")')
    print()
    print("2. Update your code to check sklearn version:")
    print(f'   assert sklearn.__version__ == "{skl_version}"')
    print()
    print("3. Test the model with a sample document:")
    print("   X = vectorizer.transform([\"your text here\"])")
    print()


if __name__ == "__main__":
    main()

