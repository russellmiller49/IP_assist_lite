#!/usr/bin/env python3
"""Find large files in the repository."""
import os
from pathlib import Path

def find_large_files(root_dir='.', min_size_mb=0.5):
    """Find files larger than min_size_mb."""
    large_files = []
    min_size_bytes = min_size_mb * 1024 * 1024
    
    for root, dirs, files in os.walk(root_dir):
        # Skip .git directory
        if '.git' in root:
            continue
        
        for file in files:
            filepath = os.path.join(root, file)
            try:
                size = os.path.getsize(filepath)
                if size > min_size_bytes:
                    size_mb = size / (1024 * 1024)
                    large_files.append((size_mb, filepath))
            except (OSError, PermissionError):
                pass
    
    large_files.sort(reverse=True)
    return large_files

if __name__ == '__main__':
    files = find_large_files()
    print(f"Found {len(files)} files larger than 0.5MB:\n")
    for size_mb, path in files[:50]:
        print(f"{size_mb:8.2f} MB  {path}")
