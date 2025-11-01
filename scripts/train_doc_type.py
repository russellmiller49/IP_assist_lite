#!/usr/bin/env python3
"""Train the document-type classifier and persist model artefacts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable, List, Tuple

import joblib
from sklearn import __version__ as sklearn_version
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC


def _load_examples(
    data_path: Path,
    *,
    text_field: str,
    label_field: str,
) -> Tuple[List[str], List[str]]:
    texts: List[str] = []
    labels: List[str] = []

    if data_path.suffix.lower() == ".jsonl":
        for line in data_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if text_field not in record or label_field not in record:
                raise ValueError(f"Record missing required fields {text_field}/{label_field}: {record}")
            texts.append(str(record[text_field]))
            labels.append(str(record[label_field]))
    else:
        with data_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if text_field not in row or label_field not in row:
                    raise ValueError(f"Row missing required fields {text_field}/{label_field}: {row}")
                texts.append(str(row[text_field]))
                labels.append(str(row[label_field]))

    if not texts:
        raise ValueError("Training dataset is empty.")
    return texts, labels


def _build_pipeline(min_df: int) -> Pipeline:
    return Pipeline(
        steps=[
            (
                "tfidf",
                TfidfVectorizer(
                    ngram_range=(1, 2),
                    min_df=min_df,
                    max_df=0.9,
                    sublinear_tf=True,
                    lowercase=True,
                ),
            ),
            ("clf", LinearSVC()),
        ]
    )


def _write_manifest(manifest_path: Path, *, labels: Iterable[str]) -> None:
    payload = {
        "sklearn_version": sklearn_version,
        "schema_version": "1",
        "labels": sorted(set(labels)),
        "model_path": "model.joblib",
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Medparse document-type classifier.")
    parser.add_argument("input", type=Path, help="Path to labeled training data (CSV or JSONL).")
    parser.add_argument(
        "--text-field",
        default="text",
        help="Field name containing training text (default: text).",
    )
    parser.add_argument(
        "--label-field",
        default="label",
        help="Field name containing labels (default: label).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("models/doc_type"),
        help="Directory to write model.joblib and MANIFEST.json.",
    )
    parser.add_argument(
        "--min-df",
        type=int,
        default=2,
        help="Minimum document frequency for the TF-IDF vectorizer (default: 2).",
    )
    args = parser.parse_args()

    texts, labels = _load_examples(
        args.input,
        text_field=args.text_field,
        label_field=args.label_field,
    )

    pipeline = _build_pipeline(args.min_df)
    pipeline.fit(texts, labels)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "model.joblib"
    joblib.dump(pipeline, model_path)
    _write_manifest(output_dir / "MANIFEST.json", labels=labels)
    print(f"Saved doc-type model to {model_path} (labels={sorted(set(labels))})")


if __name__ == "__main__":
    main()
