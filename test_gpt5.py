#!/usr/bin/env python3
"""
Simple GPT-5 Test Script for IP Assist Lite
Run this to test GPT-5 integration without Gradio
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from llm.gpt5_medical import GPT5MedicalGenerator, num_tokens
from safety.contraindication_tool import CONTRAINDICATION_TOOL, FORCE_DECISION_TOOL
import json
from datetime import datetime

def test_medical_query():
    """Test basic medical query generation."""
    print("\n" + "="*60)
    print("TEST 1: Medical Query Generation")
    print("="*60)
    
    queries = [
        "What are the contraindications for rigid bronchoscopy?",
        "CPT code for EBUS-TBNA with needle aspiration",
        "Management of massive hemoptysis >300ml"
    ]
    
    for model in ["gpt-5-mini"]:  # Start with mini for testing
        print(f"\n📊 Testing {model}")
        gen = GPT5MedicalGenerator(
            model=model,
            max_output=2000,
            reasoning_effort="medium",
            verbosity="low"
        )
        
        for query in queries[:1]:  # Test first query
            print(f"\n❓ Query: {query}")
            print(f"   Tokens: {num_tokens(query)}")
            
            try:
                start = datetime.now()
                result = gen.generate(
                    system="You are an expert in interventional pulmonology. Be concise and accurate.",
                    user=query
                )
                elapsed = (datetime.now() - start).total_seconds()
                
                print(f"✅ Response ({elapsed:.2f}s):")
                print("-" * 40)
                print(result.get("text", "No response")[:500])
                if len(result.get("text", "")) > 500:
                    print("... [truncated]")
                print("-" * 40)
                
            except Exception as e:
                print(f"❌ Error: {e}")

def test_safety_decision():
    """Test structured safety decision."""
    print("\n" + "="*60)
    print("TEST 2: Safety Decision with JSON Output")
    print("="*60)
    
    gen = GPT5MedicalGenerator(
        model="gpt-5-mini",
        max_output=1000,
        reasoning_effort="high",
        verbosity="low"
    )
    
    scenarios = [
        ("Rigid bronchoscopy", "85-year-old with severe COPD, FEV1 25%, on home oxygen"),
    ]
    
    for procedure, context in scenarios:
        print(f"\n🏥 Procedure: {procedure}")
        print(f"👤 Patient: {context}")
        
        try:
            result = gen.generate(
                system="You are a medical safety evaluator. Analyze the procedure and patient context. You MUST use the emit_decision tool.",
                user=f"Procedure: {procedure}\nPatient: {context}\n\nEvaluate safety.",
                tools=CONTRAINDICATION_TOOL,
                tool_choice=FORCE_DECISION_TOOL
            )
            
            tool_calls = result.get("tool_calls", [])
            if tool_calls:
                decision = tool_calls[0]
                print("\n📋 Safety Decision:")
                print(json.dumps(decision, indent=2))
            else:
                print("\n📝 Text Response:")
                print(result.get("text", "No response"))
                
        except Exception as e:
            print(f"❌ Error: {e}")

def test_model_comparison():
    """Compare different model sizes."""
    print("\n" + "="*60)
    print("TEST 3: Model Comparison")
    print("="*60)
    
    query = "List 3 main contraindications for bronchoscopy"
    models = ["gpt-5-nano", "gpt-5-mini", "gpt-5"]
    
    print(f"\n❓ Query: {query}")
    print("\nComparing models...")
    
    for model in models:
        print(f"\n🤖 {model}:")
        try:
            gen = GPT5MedicalGenerator(
                model=model,
                max_output=500,
                reasoning_effort="low",
                verbosity="low"
            )
            
            start = datetime.now()
            result = gen.generate(
                system="List contraindications concisely.",
                user=query
            )
            elapsed = (datetime.now() - start).total_seconds()
            
            response = result.get("text", "No response")
            print(f"   Time: {elapsed:.2f}s")
            print(f"   Length: {len(response)} chars")
            print(f"   Response: {response[:200]}...")
            
        except Exception as e:
            print(f"   Error: {e}")

def interactive_test():
    """Interactive testing mode."""
    print("\n" + "="*60)
    print("INTERACTIVE GPT-5 TEST MODE")
    print("="*60)
    print("\nCommands:")
    print("  'quit' - Exit")
    print("  'model:<name>' - Switch model (gpt-5, gpt-5-mini, gpt-5-nano)")
    print("  Any other text - Send as query\n")
    
    current_model = "gpt-5-mini"
    gen = GPT5MedicalGenerator(model=current_model)
    
    while True:
        try:
            query = input(f"\n[{current_model}]> ").strip()
            
            if query.lower() == 'quit':
                break
            elif query.startswith('model:'):
                current_model = query.split(':')[1].strip()
                gen = GPT5MedicalGenerator(model=current_model)
                print(f"✅ Switched to {current_model}")
                continue
            elif not query:
                continue
            
            print("\n⏳ Processing...")
            start = datetime.now()
            result = gen.generate(
                system="You are an expert in interventional pulmonology. Provide accurate medical information.",
                user=query
            )
            elapsed = (datetime.now() - start).total_seconds()
            
            print(f"\n📝 Response ({elapsed:.2f}s):")
            print("-" * 60)
            print(result.get("text", "No response"))
            print("-" * 60)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║         GPT-5 Medical Integration Test Suite              ║
║                IP Assist Lite                             ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    import argparse
    parser = argparse.ArgumentParser(description="Test GPT-5 integration")
    parser.add_argument("--test", choices=["query", "safety", "compare", "all"], 
                       default="all", help="Which test to run")
    parser.add_argument("--interactive", "-i", action="store_true", 
                       help="Run interactive mode")
    args = parser.parse_args()
    
    if args.interactive:
        interactive_test()
    elif args.test == "query":
        test_medical_query()
    elif args.test == "safety":
        test_safety_decision()
    elif args.test == "compare":
        test_model_comparison()
    else:  # all
        test_medical_query()
        test_safety_decision()
        test_model_comparison()
        print("\n✅ All tests completed!")
        print("\nRun with -i flag for interactive mode: python test_gpt5.py -i")