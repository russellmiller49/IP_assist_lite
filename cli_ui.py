#!/usr/bin/env python3
"""
Simple CLI interface for IP Assist Lite
Use this when web UIs fail
"""

import sys
import os
from pathlib import Path
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ui.gradio_app import get_orchestrator, process_query, search_cpt, get_system_stats

def main():
    print("🏥 IP Assist Lite - CLI Interface")
    print("=" * 50)
    
    # Initialize orchestrator
    print("🔄 Initializing orchestrator...")
    try:
        orch = get_orchestrator()
        print("✅ Orchestrator ready")
    except Exception as e:
        print(f"❌ Failed to initialize orchestrator: {e}")
        return
    
    while True:
        print("\nOptions:")
        print("1. Query Assistant")
        print("2. CPT Code Search")
        print("3. System Statistics")
        print("4. Exit")
        
        choice = input("\nEnter your choice (1-4): ").strip()
        
        if choice == "1":
            query = input("\nEnter your medical query: ").strip()
            if query:
                print("\n🔄 Processing query...")
                try:
                    html, status, metadata = process_query(query, True, 5)
                    print(f"\n✅ Status: {status}")
                    print(f"\n📄 Response:")
                    print("-" * 50)
                    # Simple text extraction from HTML
                    import re
                    text_response = re.sub(r'<[^>]+>', '', html)
                    print(text_response)
                    print("-" * 50)
                except Exception as e:
                    print(f"❌ Error: {e}")
        
        elif choice == "2":
            cpt = input("\nEnter CPT code: ").strip()
            if cpt:
                print("\n🔄 Searching CPT code...")
                try:
                    result = search_cpt(cpt)
                    print(f"\n📄 CPT Results:")
                    print("-" * 50)
                    import re
                    text_result = re.sub(r'<[^>]+>', '', result)
                    print(text_result)
                    print("-" * 50)
                except Exception as e:
                    print(f"❌ Error: {e}")
        
        elif choice == "3":
            print("\n🔄 Loading statistics...")
            try:
                stats = get_system_stats()
                print(f"\n📊 System Statistics:")
                print("-" * 50)
                import re
                text_stats = re.sub(r'<[^>]+>', '', stats)
                print(text_stats)
                print("-" * 50)
            except Exception as e:
                print(f"❌ Error: {e}")
        
        elif choice == "4":
            print("\n👋 Goodbye!")
            break
        
        else:
            print("\n❌ Invalid choice. Please enter 1-4.")

if __name__ == "__main__":
    main()
