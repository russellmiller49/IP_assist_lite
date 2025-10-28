#!/bin/bash
# Verify environment configuration is set up correctly

echo "=== Environment Verification ==="
echo ""

# Check .env file exists
if [ -f "$(pwd)/.env" ]; then
    echo "✓ .env file found"
    
    # Check UMLS_API_KEY is in .env
    if grep -q "UMLS_API_KEY=" "$(pwd)/.env"; then
        echo "✓ UMLS_API_KEY found in .env"
        key=$(grep "UMLS_API_KEY=" "$(pwd)/.env" | cut -d '=' -f2)
        if [ -n "$key" ]; then
            echo "  Value: ${key:0:20}..."
        else
            echo "  ⚠ Value appears to be empty"
        fi
    else
        echo "✗ UMLS_API_KEY not found in .env"
    fi
    
    # Check QUICKUMLS_PATH is in .env
    if grep -q "QUICKUMLS_PATH=" "$(pwd)/.env"; then
        echo "✓ QUICKUMLS_PATH found in .env"
        path=$(grep "QUICKUMLS_PATH=" "$(pwd)/.env" | cut -d '=' -f2)
        echo "  Value: $path"
        
        # Check if path exists and is readable
        if [ -d "$path" ]; then
            echo "  ✓ Directory exists"
            if [ -r "$path" ]; then
                echo "  ✓ Directory is readable"
            else
                echo "  ✗ Directory is not readable (permissions issue)"
            fi
        else
            echo "  ⚠ Directory does not exist (will be created when building QuickUMLS)"
        fi
    else
        echo "✗ QUICKUMLS_PATH not found in .env"
    fi
else
    echo "✗ .env file not found"
fi

echo ""
echo "=== Python Loading Test ==="
echo ""

# Test loading via python-dotenv
python3 << 'ENDPY'
import os
import sys

try:
    from dotenv import load_dotenv
    
    # Load from current directory
    load_dotenv(dotenv_path='.env')
    
    print("✓ python-dotenv loaded")
    
    # Check UMLS_API_KEY
    umls_key = os.getenv('UMLS_API_KEY')
    if umls_key:
        print(f"✓ UMLS_API_KEY accessible via Python")
        print(f"  Value: {umls_key[:20]}...")
    else:
        print("✗ UMLS_API_KEY not accessible via Python")
    
    # Check QUICKUMLS_PATH
    quickumls_path = os.getenv('QUICKUMLS_PATH')
    if quickumls_path:
        print(f"✓ QUICKUMLS_PATH accessible via Python")
        print(f"  Value: {quickumls_path}")
        
        # Check if readable
        if os.path.exists(quickumls_path):
            print("  ✓ Directory exists")
            if os.access(quickumls_path, os.R_OK):
                print("  ✓ Directory is readable")
            else:
                print("  ✗ Directory not readable")
        else:
            print("  ⚠ Directory does not exist yet")
    else:
        print("✗ QUICKUMLS_PATH not accessible via Python")
        
except ImportError:
    print("✗ python-dotenv not installed")
    print("  Install: pip install python-dotenv")
except Exception as e:
    print(f"⚠ Error loading dotenv: {e}")
ENDPY

echo ""
echo "=== Verification Complete ==="

