#!/usr/bin/env python3
import subprocess
import sys
import os

def run_command(cmd):
    """Run a command and return the output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def main():
    # Change to project directory
    os.chdir('/home/rjm/projects/IP_assist_lite')
    
    # Activate conda environment and run git commands
    commands = [
        'conda activate ipass2',
        'git checkout main',
        'git reset --hard chore/gpt5-retrieval-chunking-upgrade',
        'git log --oneline -1'
    ]
    
    for cmd in commands:
        print(f"Running: {cmd}")
        returncode, stdout, stderr = run_command(cmd)
        if returncode != 0:
            print(f"Error: {stderr}")
        else:
            print(f"Output: {stdout}")
    
    print("Main branch replacement completed!")

if __name__ == "__main__":
    main()
