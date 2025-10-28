# Conda Initialization Fix

You encountered the error: `CondaError: Run 'conda init' before 'conda activate'`

This means conda hasn't been initialized in your shell. Here are two solutions:

---

## Solution 1: Initialize Conda (Recommended)

Run this once to initialize conda for your shell:

```bash
# For bash
conda init bash

# Then restart your terminal or source it
source ~/.bashrc
```

After this, you can run the automated setup script:

```bash
bash scripts/setup_environments.sh
```

---

## Solution 2: Use Manual Setup Script (No conda init needed)

I've created an alternative script that doesn't require conda activation:

```bash
bash scripts/manual_setup.sh
```

This script uses `conda run` instead of `conda activate`, which doesn't require initialization.

---

## Quick Manual Setup (No Script)

If you prefer to do it step-by-step manually:

### 1. Initialize conda (once)

```bash
conda init bash
source ~/.bashrc
```

### 2. Create environment

```bash
conda create -n ipassist-py311 python=3.11 -y
```

### 3. Activate and install

```bash
conda activate ipassist-py311

# Upgrade pip
python -m pip install --upgrade pip setuptools wheel

# Install packages
pip install "torch==2.9.0"
pip install "PyMuPDF==1.24.9" "pdfplumber==0.11.7"
pip install "spacy==3.7.4" "scispacy==0.5.4"
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz
pip install "nmslib==2.1.2" "typer>=0.12,<1.0" "tqdm" "rich" "pandas>=2.0" "numpy>=1.26"
pip install "scikit-learn==1.1.2" "joblib>=1.3"

# Install IP Assist Lite
cd /home/rjm/projects/IP_assist_lite
pip install -e .
```

### 4. Verify

```bash
python scripts/doctor.py
```

---

## What Happened?

The error occurred because:
1. The setup script uses `conda activate` commands
2. Your shell hasn't been configured to recognize conda commands
3. This happens when conda is installed but not initialized in your shell

## Recommendation

**Use Solution 1** (initialize conda). It's a one-time setup that makes conda work everywhere:

```bash
conda init bash
source ~/.bashrc
bash scripts/setup_environments.sh
```

This will work for all future conda operations.

