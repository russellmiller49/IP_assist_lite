#!/usr/bin/env python3
"""
Create a minimal branch by removing large non-essential files (AUTO MODE).
This version runs without prompts for automation.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path("/home/rjm/projects/IP_assist_lite")

# Same patterns as main script
REMOVE_PATTERNS = [
    "data/Input pdfs/*.pdf",
    "data/seed/*.pdf",
    "data/vectors/*.npy",
    "data/processed/*.json",
    "data/chunks/*.jsonl",
    "data/structured_knowledge/*.json",
    "data/term_index/*.jsonl",
    "data/registry.jsonl",
    "bin/qdrant",
    "models/*.joblib",
    ".hypothesis/**/*",
    "out/*.json",
    "anomaly_reports/*",
    "Claude_chat_transcripts/**/*",
    "cursor_exported_coversations/**/*",
    "2025-*.txt",
]

REMOVE_DIRS = [
    ".hypothesis",
    "anomaly_reports",
    "Claude_chat_transcripts",
    "cursor_exported_coversations",
]

KEEP_PATTERNS = [
    "data/schema/*",
    "data/templates/*",
    "data/fixtures/*",
    "data/ip_coding_billing.json",
    "data/ip_templates.json",
    "data/kb_analysis_report.json",
    "*.py",
    "*.yaml",
    "*.yml",
    "*.md",
    "*.sh",
    "*.toml",
    "*.ini",
    "src/**/*",
    "medparse/**/*",
    "scripts/**/*",
    "tests/**/*.py",
    "tests/**/*.json",
    "configs/**/*",
    "documentation/**/*",
    "docs/**/*",
    ".gitignore",
    ".gitattributes",
    "README.md",
    "pyproject.toml",
    "pytest.ini",
    "Makefile",
    "requirements*.txt",
    "docker/**/*",
]

def run_cmd(cmd, check=True):
    """Run a shell command."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=REPO_DIR)
    if check and result.returncode != 0:
        print(f"Error running: {cmd}")
        print(f"Error: {result.stderr}")
        return None
    return result

def get_current_branch():
    """Get current git branch."""
    result = run_cmd("git branch --show-current", check=False)
    return result.stdout.strip() if result and result.returncode == 0 else "unknown"

def should_keep_file(filepath):
    """Check if a file should be kept."""
    import fnmatch
    filepath_str = str(filepath)
    for pattern in KEEP_PATTERNS:
        pattern_clean = pattern.replace('**/', '').replace('**', '*')
        if fnmatch.fnmatch(filepath_str, pattern_clean) or fnmatch.fnmatch(os.path.basename(filepath_str), pattern_clean):
            return True
    return False

def get_files_to_remove():
    """Get list of files to remove."""
    files_to_remove = []
    import glob
    
    # Add files matching remove patterns
    for pattern in REMOVE_PATTERNS:
        matches = glob.glob(os.path.join(REPO_DIR, pattern), recursive=True)
        for match in matches:
            if os.path.isfile(match):
                rel_path = os.path.relpath(match, REPO_DIR)
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
    
    # Find large files in data/
    data_dir = os.path.join(REPO_DIR, "data")
    if os.path.exists(data_dir):
        for root, dirs, files in os.walk(data_dir):
            rel_root = os.path.relpath(root, REPO_DIR)
            if any(essential in rel_root for essential in ["schema", "templates", "fixtures"]):
                continue
            
            for file in files:
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, REPO_DIR)
                
                if should_keep_file(rel_path) or rel_path in files_to_remove:
                    continue
                
                try:
                    size = os.path.getsize(filepath)
                    if size > 500 * 1024:
                        files_to_remove.append(rel_path)
                except (OSError, PermissionError):
                    pass
    
    # Remove conversation transcript files
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
    print("=== IP Assist Lite - Minimal Branch Creator (AUTO) ===\n")
    
    if not os.path.exists(os.path.join(REPO_DIR, ".git")):
        print("Error: Not a git repository!")
        sys.exit(1)
    
    current_branch = get_current_branch()
    print(f"Current branch: {current_branch}\n")
    
    minimal_branch = sys.argv[1] if len(sys.argv) > 1 else f"{current_branch}-minimal"
    print(f"Minimal branch name: {minimal_branch}\n")
    
    # Check if branch exists
    result = run_cmd(f"git show-ref --verify --quiet refs/heads/{minimal_branch}", check=False)
    if result and result.returncode == 0:
        print(f"Branch {minimal_branch} exists. Deleting...")
        run_cmd(f"git branch -D {minimal_branch}", check=False)
    
    # Create new branch
    print(f"Creating branch: {minimal_branch}")
    result = run_cmd(f"git checkout -b {minimal_branch}")
    if not result:
        print("Failed to create branch!")
        sys.exit(1)
    
    # Get files to remove
    print("\n=== Identifying files to remove ===")
    files_to_remove = get_files_to_remove()
    print(f"Found {len(files_to_remove)} files to remove")
    
    if files_to_remove:
        print("\nSample files to remove (first 20):")
        for f in files_to_remove[:20]:
            print(f"  {f}")
        if len(files_to_remove) > 20:
            print(f"  ... and {len(files_to_remove) - 20} more")
    
    # Calculate current size
    result = run_cmd("du -sh .", check=False)
    current_size = result.stdout.split()[0] if result and result.returncode == 0 else "unknown"
    print(f"\nCurrent repository size: {current_size}")
    
    # Remove files
    print("\n=== Removing files ===")
    removed_count = 0
    for filepath in files_to_remove:
        full_path = os.path.join(REPO_DIR, filepath)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
                removed_count += 1
                if removed_count % 100 == 0:
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
    if result and result.stdout:
        print("\n=== Git status (first 20 lines) ===")
        lines = result.stdout.strip().split('\n')
        for line in lines[:20]:
            print(f"  {line}")
        if len(lines) > 20:
            print(f"  ... and {len(lines) - 20} more changes")
    
    # Calculate new size
    result = run_cmd("du -sh .", check=False)
    new_size = result.stdout.split()[0] if result and result.returncode == 0 else "unknown"
    print(f"\nNew repository size: {new_size}")
    
    # Commit
    print("\n=== Committing changes ===")
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
    
    result = run_cmd(f'git commit -m "{commit_msg}"')
    if result:
        print("\n=== Branch created successfully! ===")
        print(f"Branch: {minimal_branch}")
        print(f"\nTo push to GitHub:")
        print(f"  git push origin {minimal_branch}")
        print(f"\nTo switch back to original branch:")
        print(f"  git checkout {current_branch}")
    else:
        print("\nWarning: Commit may have failed. Check git status.")

if __name__ == "__main__":
    main()
