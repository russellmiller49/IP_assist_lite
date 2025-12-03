#!/bin/bash
# Simple wrapper to run the minimal branch script

cd "$(dirname "$0")"
python3 create_minimal_branch.py --yes "$@"
