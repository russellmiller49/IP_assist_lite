#!/bin/bash
cd /home/rjm/projects/IP_assist_lite
conda activate ipass2

echo "Current branch: $(git branch --show-current)"
echo "Switching to main branch..."
git checkout main

echo "Replacing main branch content with chore/gpt5-retrieval-chunking-upgrade..."
git reset --hard chore/gpt5-retrieval-chunking-upgrade

echo "Verification - Main branch now points to:"
git log --oneline -1

echo "Branch replacement completed successfully!"
