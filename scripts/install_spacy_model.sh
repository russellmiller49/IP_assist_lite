#!/bin/bash
# Install en_core_sci_lg model with multiple fallback methods

set -e

ENV_NAME="medparse-py311"

echo "=== Installing en_core_sci_lg in $ENV_NAME ==="

# Method 1: Try the S3 URL with version path
echo "Method 1: Trying S3 URL with version path..."
conda run -n $ENV_NAME pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_lg-0.5.4.tar.gz && echo "✓ Success!" && exit 0 || echo "✗ Failed"

# Method 2: Install via scispacy package
echo ""
echo "Method 2: Trying scispacy package installation..."
conda run -n $ENV_NAME pip install scispacy || echo "Already installed"

# Method 3: Download and install manually
echo ""
echo "Method 3: Trying direct tar.gz from different path..."
conda run -n $ENV_NAME pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/en_core_sci_lg-0.5.4.tar.gz && echo "✓ Success!" && exit 0 || echo "✗ Failed"

# Method 4: Try installing from PyPI
echo ""
echo "Method 4: Checking if available via pip directly..."
conda run -n $ENV_NAME pip install en_core_sci_lg==0.5.4 && echo "✓ Success!" && exit 0 || echo "✗ Not on PyPI"

# Method 5: Manual download
echo ""
echo "Method 5: Attempting manual download from GitHub..."
cd /tmp
wget -q https://github.com/allenai/scispacy/raw/master/en_core_sci_lg.tar.gz && \
  conda run -n $ENV_NAME pip install en_core_sci_lg.tar.gz && echo "✓ Success!" && rm en_core_sci_lg.tar.gz && exit 0 || echo "✗ Failed"

echo ""
echo "All methods failed. Please check scispacy GitHub repository for latest installation instructions."
echo "https://github.com/allenai/scispacy"

