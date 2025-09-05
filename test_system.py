#!/usr/bin/env python
"""
Quick test script to verify the system is working
"""
import sys
from pathlib import Path

def test_imports():
    """Test that all required imports work."""
    print("Testing imports...")
    try:
        import torch
        print(f"✓ PyTorch: {torch.__version__} (CUDA: {torch.cuda.is_available()})")
        
        import transformers
        print(f"✓ Transformers: {transformers.__version__}")
        
        import sentence_transformers
        print(f"✓ Sentence Transformers: {sentence_transformers.__version__}")
        
        import qdrant_client
        print(f"✓ Qdrant Client: {qdrant_client.__version__}")
        
        import fastapi
        print(f"✓ FastAPI: {fastapi.__version__}")
        
        import gradio
        print(f"✓ Gradio: {gradio.__version__}")
        
        import langgraph
        print(f"✓ LangGraph: {langgraph.__version__}")
        
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_data_prep():
    """Test data preparation module."""
    print("\nTesting data preparation...")
    try:
        sys.path.append('src')
        from prep.data_preparer_v12 import DataPreparerV12
        
        preparer = DataPreparerV12()
        files = list(preparer.input_dir.glob("*.json"))[:1]
        
        if files:
            print(f"  Found {len(list(preparer.input_dir.glob('*.json')))} raw files")
            print("✓ Data preparer initialized successfully")
            return True
        else:
            print("✗ No raw data files found")
            return False
    except Exception as e:
        print(f"✗ Data prep error: {e}")
        return False

def test_gpu():
    """Test GPU availability and memory."""
    print("\nTesting GPU...")
    try:
        import torch
        if torch.cuda.is_available():
            device = torch.cuda.get_device_properties(0)
            print(f"  GPU: {device.name}")
            print(f"  VRAM: {device.total_memory / 1e9:.1f} GB")
            print(f"  CUDA: {torch.version.cuda}")
            print("✓ GPU ready for inference")
            return True
        else:
            print("✗ No GPU available (CPU mode will be slower)")
            return False
    except Exception as e:
        print(f"✗ GPU test error: {e}")
        return False

def test_directories():
    """Test that required directories exist."""
    print("\nTesting directory structure...")
    required_dirs = [
        "data/raw",
        "data/processed",
        "data/chunks", 
        "data/vectors",
        "data/term_index",
        "src/ip_assistant",
        "src/prep",
        "src/extract",
        "src/index",
        "configs"
    ]
    
    all_exist = True
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists():
            print(f"  ✓ {dir_path}")
        else:
            print(f"  ✗ {dir_path} missing")
            all_exist = False
    
    return all_exist

def main():
    """Run all tests."""
    print("=" * 50)
    print("IP Assist Lite - System Test")
    print("=" * 50)
    
    results = {
        "Imports": test_imports(),
        "Directories": test_directories(),
        "Data Prep": test_data_prep(),
        "GPU": test_gpu(),
    }
    
    print("\n" + "=" * 50)
    print("Test Summary:")
    print("=" * 50)
    
    for test, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test:15} {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n🎉 All tests passed! System ready to use.")
        print("\nNext steps:")
        print("1. Run 'make prep' to process documents")
        print("2. Run 'make chunk' to create chunks")
        print("3. Run 'make embed' to generate embeddings")
        print("4. Run 'make docker-up' to start Qdrant")
        print("5. Run 'make index' to build the index")
    else:
        print("\n⚠️  Some tests failed. Please fix issues before proceeding.")
        if not results["Imports"]:
            print("\nRun: pip install -r requirements.txt")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())