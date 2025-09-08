#!/usr/bin/env python3
"""
Test the backend API directly without Gradio frontend
"""
import requests
import json
import time

# Start the Gradio app first: python src/ui/gradio_app.py
API_URL = "http://localhost:7860"

def test_api_health():
    """Check if the API is running."""
    try:
        response = requests.get(f"{API_URL}/api/health", timeout=5)
        if response.status_code == 200:
            print("✅ API is running")
            return True
    except:
        pass
    print("❌ API is not running. Start it with: python src/ui/gradio_app.py")
    return False

def test_query_endpoint():
    """Test the main query endpoint."""
    print("\n" + "="*50)
    print("Testing Query Endpoint")
    print("="*50)
    
    # The Gradio API endpoint for the query function
    endpoint = f"{API_URL}/api/predict/"
    
    test_queries = [
        "What are contraindications for bronchoscopy?",
        "CPT code for EBUS-TBNA",
        "Management of massive hemoptysis"
    ]
    
    for query in test_queries:
        print(f"\n📝 Query: {query}")
        
        # Gradio expects data in a specific format
        payload = {
            "data": [
                query,      # query text
                True,       # use_reranker
                5          # top_k
            ],
            "fn_index": 0  # First function in the interface
        }
        
        try:
            start = time.time()
            response = requests.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            elapsed = time.time() - start
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Response received in {elapsed:.2f}s")
                
                # Parse the response
                if "data" in result and len(result["data"]) > 0:
                    answer = result["data"][0]
                    print(f"Answer preview: {answer[:200]}...")
                    
                    # Check if it's cached (would be in metadata)
                    if "⚡ Cached" in answer:
                        print("   (Cached result)")
            else:
                print(f"❌ Error: {response.status_code}")
                print(f"   {response.text[:200]}")
                
        except Exception as e:
            print(f"❌ Request failed: {e}")

def test_cpt_search():
    """Test CPT code search endpoint."""
    print("\n" + "="*50)
    print("Testing CPT Search")
    print("="*50)
    
    endpoint = f"{API_URL}/api/predict/"
    
    cpt_codes = ["31622", "31628", "31645"]
    
    for code in cpt_codes:
        print(f"\n🔍 CPT Code: {code}")
        
        payload = {
            "data": [code],
            "fn_index": 1  # Second function (CPT search)
        }
        
        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ CPT info retrieved")
                if "data" in result:
                    info = result["data"][0]
                    # CPT info is returned as HTML
                    if "Description:" in info:
                        print("   Found CPT description")
            else:
                print(f"❌ Error: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Request failed: {e}")

def test_direct_orchestrator():
    """Test the orchestrator directly without Gradio."""
    print("\n" + "="*50)
    print("Testing Direct Orchestrator Access")
    print("="*50)
    
    # Import and use the orchestrator directly
    import sys
    sys.path.insert(0, '/Users/russellmiller/Projects/IP_assist_lite/src')
    
    try:
        from ui.gradio_app import get_orchestrator
        
        print("🔥 Initializing orchestrator...")
        orchestrator = get_orchestrator()
        
        if orchestrator:
            print("✅ Orchestrator ready")
            
            # Test a query directly
            query = "What is the CPT code for bronchoscopy with biopsy?"
            print(f"\n📝 Direct query: {query}")
            
            # Call the retriever directly
            results = orchestrator.retriever.search(
                query=query,
                top_k=3,
                use_reranker=True
            )
            
            print(f"✅ Retrieved {len(results)} results")
            for i, result in enumerate(results[:2], 1):
                print(f"\n{i}. Score: {result.score:.3f}")
                print(f"   Source: {result.metadata.get('source', 'Unknown')}")
                print(f"   Text: {result.text[:150]}...")
        else:
            print("❌ Failed to initialize orchestrator")
            
    except Exception as e:
        print(f"❌ Direct access failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🧪 Backend API Test Suite")
    print("="*50)
    
    # Check if API is running
    if not test_api_health():
        print("\nTo start the backend:")
        print("1. Open a new terminal")
        print("2. Run: conda activate ipass")
        print("3. Run: python src/ui/gradio_app.py")
        print("4. Ignore the frontend errors - the API will still work")
        print("\nThen run this test again.")
    else:
        # Run tests
        test_query_endpoint()
        test_cpt_search()
    
    # Always test direct access
    test_direct_orchestrator()
    
    print("\n✨ Test suite completed!")