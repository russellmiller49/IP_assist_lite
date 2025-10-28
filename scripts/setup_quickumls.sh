#!/bin/bash
# Setup guide for QuickUMLS

echo "=== QuickUMLS Setup Instructions ==="
echo ""

echo "To use QuickUMLS, you need to:"
echo ""
echo "1. Get UMLS License"
echo "   https://www.nlm.nih.gov/research/umls/license.html"
echo ""
echo "2. Download UMLS Data (requires license)"
echo "   https://www.nlm.nih.gov/research/umls/index.html"
echo "   Download the Metathesaurus files"
echo ""
echo "3. Choose a location for your QuickUMLS database"
echo "   Recommended: ~/quickumls_data or /data/quickumls"
echo ""
echo "4. Build the QuickUMLS database:"
echo ""
echo "   conda activate medparse-py311"
echo "   python -m quickumls.install \\"
echo "     /path/to/umls/metathesaurus \\"
echo "     ~/quickumls_data"
echo ""
echo "5. Set the environment variable:"
echo ""
echo "   For current session:"
echo "   export QUICKUMLS_PATH=$HOME/quickumls_data"
echo ""
echo "   To make permanent, add to ~/.bashrc:"
echo "   echo 'export QUICKUMLS_PATH=$HOME/quickumls_data' >> ~/.bashrc"
echo "   source ~/.bashrc"
echo ""
echo "6. Verify installation:"
echo "   python << 'ENDPY'"
echo "   from quickumls import QuickUMLS"
echo "   matcher = QuickUMLS(qf="$HOME/quickumls_data")"
echo "   print('✓ QuickUMLS ready!')"
echo "   ENDPY"
echo ""

# Check if path is already set
if [ -n "$QUICKUMLS_PATH" ]; then
    echo "Current QUICKUMLS_PATH: $QUICKUMLS_PATH"
    
    # Check if the path exists
    if [ -d "$QUICKUMLS_PATH" ]; then
        echo "✓ Path exists and is accessible"
    else
        echo "⚠ Path does not exist - you may need to build the database first"
    fi
else
    echo "QUICKUMLS_PATH is not set"
    echo ""
    echo "Would you like to set it now? (recommended location: $HOME/quickumls_data)"
    echo "1. Set path (will add to ~/.bashrc)"
    echo "2. Skip for now"
    read -p "Choice [1-2]: " choice
    
    if [ "$choice" == "1" ]; then
        QUICKUMLS_DEFAULT="$HOME/quickumls_data"
        echo ""
        read -p "Enter QuickUMLS database path [$QUICKUMLS_DEFAULT]: " umls_path
        umls_path=${umls_path:-$QUICKUMLS_DEFAULT}
        
        # Add to bashrc
        if ! grep -q "QUICKUMLS_PATH" ~/.bashrc 2>/dev/null; then
            echo "" >> ~/.bashrc
            echo "# QuickUMLS configuration" >> ~/.bashrc
            echo "export QUICKUMLS_PATH=$umls_path" >> ~/.bashrc
            echo "✓ Added to ~/.bashrc"
            echo ""
            echo "Now run: source ~/.bashrc"
        else
            echo "⚠ QUICKUMLS_PATH already set in ~/.bashrc"
        fi
        
        # Set for current session
        export QUICKUMLS_PATH=$umls_path
        echo "✓ Set for current session: $QUICKUMLS_PATH"
    fi
fi

