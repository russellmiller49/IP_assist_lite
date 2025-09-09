#!/usr/bin/env python3
"""
Smoke test for GPT-5 integration in IP Assist Lite
Tests both direct OpenAI SDK and our wrapper implementation
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_direct_openai_sdk():
    """Test direct OpenAI SDK with Responses API"""
    print("=" * 60)
    print("TEST 1: Direct OpenAI SDK with Responses API")
    print("=" * 60)
    
    from openai import OpenAI
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    models_to_test = ["gpt-5", "gpt-5-mini", "gpt-5-nano"]
    prompt = "Summarize the key contraindications to flexible bronchoscopy in adults and note any absolute vs relative items."
    
    for model in models_to_test:
        print(f"\nTesting {model}...")
        try:
            resp = client.responses.create(
                model=model,
                instructions="You are a careful interventional pulmonology assistant. Be specific and structured.",
                input=prompt,
                max_output_tokens=600,
                reasoning={"effort": "medium"},
            )
            
            # Check for output_text attribute
            output_text = getattr(resp, "output_text", None)
            print(f"✓ {model} Response (first 200 chars):")
            if output_text:
                print(f"  {output_text[:200]}...")
                print(f"  Full length: {len(output_text)} characters")
            else:
                print(f"  WARNING: No output_text attribute found")
                print(f"  Response type: {type(resp)}")
                print(f"  Response dir: {[x for x in dir(resp) if not x.startswith('_')][:5]}")
                
        except Exception as e:
            print(f"✗ {model} failed: {e}")
            # Try Chat Completions as fallback
            print(f"  Trying Chat Completions fallback...")
            try:
                chat_resp = client.chat.completions.create(
                    model="gpt-4o-mini",  # Use known working model
                    messages=[
                        {"role": "system", "content": "You are a medical assistant."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=600,
                    temperature=0.3
                )
                text = chat_resp.choices[0].message.content if chat_resp.choices else ""
                print(f"  ✓ Fallback worked (gpt-4o-mini): {text[:100]}...")
            except Exception as e2:
                print(f"  ✗ Fallback also failed: {e2}")

def test_gpt5medical_wrapper():
    """Test our GPT5Medical wrapper"""
    print("\n" + "=" * 60)
    print("TEST 2: GPT5Medical Wrapper")
    print("=" * 60)
    
    from src.llm.gpt5_medical import GPT5Medical
    
    models_to_test = ["gpt-5", "gpt-5-mini", "gpt-5-nano"]
    
    for model in models_to_test:
        print(f"\nTesting {model} via wrapper...")
        try:
            # Initialize with Responses API explicitly enabled
            wrapper = GPT5Medical(
                model=model,
                use_responses=True,  # Force Responses API
                max_out=800,
                reasoning_effort="medium"
            )
            
            # Test complete method
            messages = [
                {"role": "system", "content": "You are an expert in interventional pulmonology. Be detailed and specific."},
                {"role": "user", "content": "What are the main complications of transbronchial lung cryobiopsy? Include rates if known."}
            ]
            
            result = wrapper.complete(messages, temperature=0.3)
            
            print(f"✓ {model} Wrapper Response:")
            if result.get("text"):
                text = result["text"]
                print(f"  Text (first 200 chars): {text[:200]}...")
                print(f"  Full length: {len(text)} characters")
                print(f"  Used model: {result.get('used_model', 'unknown')}")
                if wrapper.last_warning_banner:
                    print(f"  Warning: {wrapper.last_warning_banner}")
            else:
                print(f"  WARNING: No text in result")
                print(f"  Result keys: {result.keys()}")
                
        except Exception as e:
            print(f"✗ {model} wrapper failed: {e}")

def test_orchestrator_integration():
    """Test the full orchestrator integration"""
    print("\n" + "=" * 60)
    print("TEST 3: Orchestrator Integration")
    print("=" * 60)
    
    from src.orchestration.langgraph_agent import IPAssistOrchestrator
    
    models_to_test = ["gpt-5-mini", "gpt-5"]
    
    for model in models_to_test:
        print(f"\nTesting orchestrator with {model}...")
        try:
            # Initialize orchestrator
            orchestrator = IPAssistOrchestrator(retriever=None, model=model)
            
            # Test LLM directly
            test_prompt = "Describe the indications for endobronchial valve placement."
            test_messages = [
                {"role": "system", "content": "You are a medical expert. Be concise but complete."}
            ]
            
            response = orchestrator.llm.generate_response(test_prompt, test_messages)
            
            print(f"✓ {model} Orchestrator Response:")
            print(f"  Response (first 200 chars): {response[:200]}...")
            print(f"  Full length: {len(response)} characters")
            print(f"  Used model: {getattr(orchestrator.llm, 'last_used_model', 'unknown')}")
            
            # Check if Responses API was used
            if orchestrator.llm.use_responses:
                print(f"  ✓ Using Responses API (as expected for GPT-5)")
            else:
                print(f"  ⚠ Using Chat Completions API (unexpected for GPT-5)")
                
        except Exception as e:
            print(f"✗ Orchestrator with {model} failed: {e}")

def main():
    """Run all smoke tests"""
    print("\n🔬 GPT-5 Integration Smoke Tests")
    print("=" * 60)
    
    # Check API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ ERROR: OPENAI_API_KEY not set in environment")
        print("Please set it in your .env file or environment")
        return
    
    print(f"✓ API Key found: {api_key[:8]}...")
    
    # Check which GPT-5 model is configured
    configured_model = os.getenv("IP_GPT5_MODEL") or os.getenv("GPT5_MODEL") or "gpt-5-mini"
    print(f"✓ Configured model: {configured_model}")
    
    # Run tests
    test_direct_openai_sdk()
    test_gpt5medical_wrapper()
    test_orchestrator_integration()
    
    print("\n" + "=" * 60)
    print("🏁 Smoke tests complete!")
    print("=" * 60)
    
    # Summary recommendations
    print("\n📋 Recommendations:")
    print("1. If GPT-5 models fail, check your API access")
    print("2. Ensure OPENAI_API_KEY has GPT-5 access enabled")
    print("3. The wrapper should automatically fall back to gpt-4o-mini if needed")
    print("4. Check that use_responses=True for GPT-5 models")
    print("5. Verify OpenAI SDK version: pip show openai (should be >=1.100.0)")

if __name__ == "__main__":
    main()