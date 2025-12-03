#!/usr/bin/env python3
"""
Create a minimal branch by removing large non-essential files.
This keeps all code but removes data files that can be regenerated.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path("/home/rjm/projects/IP_assist_lite")

# Patterns of files/directories to remove (relative to repo root)
# These are files that can be regenerated or are not essential for understanding the codebase
REMOVE_PATTERNS = [
    # PDF files (can be regenerated via ingestion)
    "data/Input pdfs/*.pdf",
    "data/seed/*.pdf",
    
    # Large data files (can be regenerated)
    "data/vectors/*.npy",  # Embeddings (can be regenerated)
    "data/processed/*.json",  # Processed data (can be regenerated)
    "data/chunks/*.jsonl",  # Chunk files (can be regenerated)
    "data/structured_knowledge/*.json",  # Structured knowledge (can be regenerated)
    "data/term_index/*.jsonl",  # Term index (can be regenerated)
    "data/registry.jsonl",  # Registry (can be regenerated)
    
    # Binary files (should be installed separately)
    "bin/qdrant",  # Qdrant binary
    
    # Model files (can be downloaded)
    "models/*.joblib",
    
    # Test and output files
    ".hypothesis/**/*",  # Hypothesis test data
    "out/*.json",  # Output files
    "anomaly_reports/*",  # Anomaly reports
    
    # Documentation artifacts
    "Claude_chat_transcripts/**/*",
    "cursor_exported_coversations/**/*",
    
    # Large text files that are transcripts
    "2025-*.txt",  # Cursor conversation exports
]

# Directories to completely remove
REMOVE_DIRS = [
    ".hypothesis",
    "anomaly_reports",
    "Claude_chat_transcripts",
    "cursor_exported_coversations",
]

# Files/directories to KEEP (even if large)
# These are essential for understanding the codebase
KEEP_PATTERNS = [
    "data/schema/*",  # Schema files are essential
    "data/templates/*",  # Templates are essential
    "data/fixtures/*",  # Test fixtures
    "data/ip_coding_billing.json",  # Essential data
    "data/ip_templates.json",  # Essential templates
    "data/kb_analysis_report.json",  # Analysis report
    "*.py",  # All Python code
    "*.yaml",  # Config files
    "*.yml",  # Config files
    "*.md",  # Documentation
    "*.sh",  # Scripts
    "*.toml",  # Config files
    "*.ini",  # Config files
    "src/**/*",  # All source code
    "medparse/**/*",  # Medparse code
    "scripts/**/*",  # Scripts
    "tests/**/*.py",  # Test code
    "tests/**/*.json",  # Test data (keep small test files)
    "configs/**/*",  # Configurations
    "documentation/**/*",  # Documentation
    "docs/**/*",  # Documentation
    ".gitignore",  # Git config
    ".gitattributes",  # Git config
    "README.md",  # README
    "pyproject.toml",  # Project config
    "pytest.ini",  # Test config
    "Makefile",  # Build config
    "requirements*.txt",  # Dependencies
    "docker/**/*",  # Docker configs
]

def run_cmd(cmd, check=True):
    """Run a shell command."""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=REPO_DIR)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result

def get_current_branch():
    """Get current git branch."""
    result = run_cmd("git branch --show-current", check=False)
    return result.stdout.strip() if result.returncode == 0 else "unknown"

def find_large_files(min_size_mb=0.5):
    """Find files larger than min_size_mb."""
    large_files = []
    min_size = min_size_mb * 1024 * 1024
    
    for root, dirs, files in os.walk(REPO_DIR):
        # Skip .git
        if '.git' in root:
            continue
        
        rel_root = os.path.relpath(root, REPO_DIR)
        if rel_root == '.':
            rel_root = ''
        
        for file in files:
            filepath = os.path.join(root, file)
            try:
                size = os.path.getsize(filepath)
                if size > min_size:
                    rel_path = os.path.relpath(filepath, REPO_DIR)
                    large_files.append((size / (1024 * 1024), rel_path))
            except (OSError, PermissionError):
                pass
    
    large_files.sort(reverse=True)
    return large_files

def should_keep_file(filepath):
    """Check if a file should be kept."""
    filepath_str = str(filepath)
    
    # Check keep patterns
    for pattern in KEEP_PATTERNS:
        if matches_pattern(filepath_str, pattern):
            return True
    
    return False

def matches_pattern(path, pattern):
    """Simple pattern matching."""
    import fnmatch
    # Convert glob to fnmatch
    pattern = pattern.replace('**/', '').replace('**', '*')
    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(os.path.basename(path), pattern)

def get_files_to_remove():
    """Get list of files to remove."""
    files_to_remove = []
    import glob
    import fnmatch
    
    # Add files matching remove patterns
    for pattern in REMOVE_PATTERNS:
        # Expand pattern using glob
        matches = glob.glob(os.path.join(REPO_DIR, pattern), recursive=True)
        for match in matches:
            if os.path.isfile(match):
                rel_path = os.path.relpath(match, REPO_DIR)
                # Double-check it's not in keep patterns
                if not should_keep_file(rel_path):
                    files_to_remove.append(rel_path)
    
    # Add entire directories
    for dir_pattern in REMOVE_DIRS:
        dir_path = os.path.join(REPO_DIR, dir_pattern)
        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            for root, dirs, files in os.walk(dir_path):
                for file in files:
                    filepath = os.path.join(root, file)
                    rel_path = os.path.relpath(filepath, REPO_DIR)
                    files_to_remove.append(rel_path)
    
    # Also find large files in data/ that aren't essential
    data_dir = os.path.join(REPO_DIR, "data")
    if os.path.exists(data_dir):
        for root, dirs, files in os.walk(data_dir):
            # Skip essential subdirs
            rel_root = os.path.relpath(root, REPO_DIR)
            if any(essential in rel_root for essential in ["schema", "templates", "fixtures"]):
                continue
            
            for file in files:
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, REPO_DIR)
                
                # Skip if should keep
                if should_keep_file(rel_path):
                    continue
                
                # Skip if already in remove list
                if rel_path in files_to_remove:
                    continue
                
                # Check size - remove if > 500KB
                try:
                    size = os.path.getsize(filepath)
                    if size > 500 * 1024:  # > 500KB
                        files_to_remove.append(rel_path)
                except (OSError, PermissionError):
                    pass
    
    # Remove conversation transcript files (2025-*.txt)
    for root, dirs, files in os.walk(REPO_DIR):
        if '.git' in root:
            continue
        for file in files:
            if file.startswith('2025-') and file.endswith('.txt'):
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, REPO_DIR)
                if rel_path not in files_to_remove:
                    files_to_remove.append(rel_path)
    
    # Remove Zone.Identifier files
    for root, dirs, files in os.walk(REPO_DIR):
        if '.git' in root:
            continue
        for file in files:
            if file.endswith(':Zone.Identifier'):
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, REPO_DIR)
                if rel_path not in files_to_remove:
                    files_to_remove.append(rel_path)
    
    return sorted(set(files_to_remove))

def main():
    print("=== IP Assist Lite - Minimal Branch Creator ===\n")
    
    # Check for --yes flag
    auto_yes = '--yes' in sys.argv or '-y' in sys.argv
    args = [a for a in sys.argv[1:] if a not in ['--yes', '-y']]
    
    # Check if in git repo
    if not os.path.exists(os.path.join(REPO_DIR, ".git")):
        print("Error: Not a git repository!")
        sys.exit(1)
    
    # Get current branch
    current_branch = get_current_branch()
    print(f"Current branch: {current_branch}\n")
    
    # Get branch name
    if len(args) > 0:
        minimal_branch = args[0]
    else:
        minimal_branch = f"{current_branch}-minimal"
    
    print(f"Minimal branch name: {minimal_branch}\n")
    
    # Check if branch exists
    result = run_cmd(f"git show-ref --verify --quiet refs/heads/{minimal_branch}", check=False)
    if result.returncode == 0:
        if auto_yes:
            print(f"Branch {minimal_branch} exists. Deleting...")
            run_cmd(f"git branch -D {minimal_branch}", check=False)
        else:
            response = input(f"Branch {minimal_branch} already exists! Delete and recreate? (y/N): ")
            if response.lower() != 'y':
                print("Aborted.")
                sys.exit(1)
            run_cmd(f"git branch -D {minimal_branch}", check=False)
    
    # Create new branch
    print(f"\nCreating branch: {minimal_branch}")
    run_cmd(f"git checkout -b {minimal_branch}")
    
    # Find large files
    print("\n=== Finding large files ===")
    large_files = find_large_files(0.5)
    print(f"Found {len(large_files)} files > 0.5MB")
    if large_files:
        print("\nTop 20 largest files:")
        for size_mb, path in large_files[:20]:
            print(f"  {size_mb:8.2f} MB  {path}")
    
    # Get files to remove
    print("\n=== Identifying files to remove ===")
    files_to_remove = get_files_to_remove()
    print(f"Found {len(files_to_remove)} files to remove")
    
    if files_to_remove:
        print("\nSample files to remove (first 30):")
        for f in files_to_remove[:30]:
            print(f"  {f}")
        if len(files_to_remove) > 30:
            print(f"  ... and {len(files_to_remove) - 30} more")
    
    # Calculate current size
    result = run_cmd("du -sh .", check=False)
    current_size = result.stdout.split()[0] if result.returncode == 0 else "unknown"
    print(f"\nCurrent repository size: {current_size}")
    
    # Confirm (skip if auto_yes)
    if not auto_yes:
        response = input("\nProceed with removal? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            sys.exit(1)
    else:
        print("\nProceeding with removal (--yes flag set)...")
    
    # Remove files
    print("\n=== Removing files ===")
    removed_count = 0
    for filepath in files_to_remove:
        full_path = os.path.join(REPO_DIR, filepath)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
                removed_count += 1
                if removed_count % 50 == 0:
                    print(f"  Removed {removed_count} files...")
            except (OSError, PermissionError) as e:
                print(f"  Warning: Could not remove {filepath}: {e}")
    
    print(f"  Removed {removed_count} files")
    
    # Remove empty directories
    print("\n=== Cleaning empty directories ===")
    for root, dirs, files in os.walk(REPO_DIR, topdown=False):
        if '.git' in root:
            continue
        try:
            if not os.listdir(root):
                os.rmdir(root)
        except (OSError, PermissionError):
            pass
    
    # Stage changes
    print("\n=== Staging changes ===")
    run_cmd("git add -A")
    
    # Show status
    result = run_cmd("git status --short", check=False)
    if result.stdout:
        print("\n=== Git status (first 30 lines) ===")
        lines = result.stdout.strip().split('\n')
        for line in lines[:30]:
            print(f"  {line}")
        if len(lines) > 30:
            print(f"  ... and {len(lines) - 30} more changes")
    
    # Calculate new size
    result = run_cmd("du -sh .", check=False)
    new_size = result.stdout.split()[0] if result.returncode == 0 else "unknown"
    print(f"\nNew repository size: {new_size}")
    
    # Commit (auto if --yes flag)
    if auto_yes:
        print("\nCommitting changes (--yes flag set)...")
        should_commit = True
    else:
        response = input("\nCommit changes? (y/N): ")
        should_commit = response.lower() == 'y'
    
    if should_commit:
        commit_msg = """Create minimal branch: Remove large non-essential files

- Removed PDF files (can be regenerated via ingestion)
- Removed processed data files (can be regenerated)
- Removed vector embeddings (can be regenerated)
- Removed binary files (bin/qdrant - install separately)
- Removed model files (can be downloaded)
- Removed test data and output files
- Kept all source code and essential configuration

This branch is optimized for code review and understanding
the repository structure without large data files."""
        
        run_cmd(f'git commit -m "{commit_msg}"')
        
        print("\n=== Branch created successfully! ===")
        print(f"Branch: {minimal_branch}")
        print(f"\nTo push to GitHub:")
        print(f"  git push origin {minimal_branch}")
        print(f"\nTo switch back to original branch:")
        print(f"  git checkout {current_branch}")
    else:
        print("\nChanges staged but not committed.")
        print("You can review with: git status")
        print("Commit manually when ready.")

if __name__ == "__main__":
    main()
