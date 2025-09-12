#!/usr/bin/env python3
"""
CLI interface for the enhanced IP Assist pipeline with conversation support.
"""

import sys
import os
import json
import argparse
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import uuid

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.retrieval.hybrid_retriever import HybridRetriever
from src.llm.gpt5_medical import GPT5Medical
from src.orchestrator.enhanced_orchestrator import EnhancedOrchestrator

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
GRAY = "\033[90m"

class EnhancedCLI:
    def __init__(self, model: str = None, qdrant_host: str = "localhost", qdrant_port: int = 6333):
        """Initialize the enhanced CLI interface."""
        print(f"{BLUE}🏥 IP Assist Lite - Enhanced CLI{RESET}")
        print(f"{GRAY}Initializing system...{RESET}\n")
        
        # Initialize retriever
        self.retriever = HybridRetriever(
            chunks_file="data/chunks/chunks.jsonl",
            qdrant_host=qdrant_host,
            qdrant_port=qdrant_port,
            collection_name="ip_medcpt"
        )
        
        # Initialize LLM client
        model = model or os.getenv("IP_GPT5_MODEL", "gpt-4o-mini")
        self.llm_client = GPT5Medical(model=model)
        
        # Initialize orchestrator
        self.orchestrator = EnhancedOrchestrator(self.retriever, self.llm_client)
        
        # Session management
        self.session_id = str(uuid.uuid4())
        self.conversation_history = []
        
        print(f"{GREEN}✓ System initialized{RESET}")
        print(f"{GRAY}Model: {model}{RESET}")
        print(f"{GRAY}Session ID: {self.session_id[:8]}...{RESET}\n")
    
    def format_response(self, result: Dict[str, Any]) -> str:
        """Format the response for terminal output."""
        lines = []
        
        # Query type and confidence
        lines.append(f"\n{CYAN}━━━ Response ━━━{RESET}")
        lines.append(f"{GRAY}Type: {result.get('query_type', 'clinical').replace('_', ' ').title()}")
        lines.append(f"Confidence: {result.get('confidence_score', 0.85):.1%}")
        lines.append(f"Model: {result.get('model_used', 'GPT-4')}{RESET}\n")
        
        # Safety flags
        if result.get("safety_flags"):
            lines.append(f"{YELLOW}⚠️  Clinical Considerations:{RESET}")
            for flag in result["safety_flags"]:
                lines.append(f"  {YELLOW}• {flag}{RESET}")
            lines.append("")
        
        # Main response
        response = result.get("response", "")
        lines.append(f"{response}")
        
        # References in full AMA format
        if result.get("citations"):
            lines.append(f"\n{CYAN}📚 References:{RESET}")
            for i, cite in enumerate(result["citations"], 1):
                # Display full AMA citation
                if 'text' in cite and cite['text']:
                    citation_text = cite['text']
                else:
                    # Build citation from components
                    author = cite.get('author', 'Unknown')
                    title = cite.get('title', '')
                    journal = cite.get('journal', '')
                    year = cite.get('year', 'N/A')
                    
                    if title and journal:
                        citation_text = f"{author}. {title}. {journal}. {year}."
                    elif title:
                        citation_text = f"{author}. {title}. {year}."
                    else:
                        citation_text = f"{author} et al. Clinical study. {year}."
                
                lines.append(f"  {GRAY}[{i}] {citation_text}{RESET}")
        elif result.get("references"):
            # Fallback to old format if citations not available
            lines.append(f"\n{CYAN}📚 References:{RESET}")
            for i, ref in enumerate(result["references"], 1):
                title = ref.get('title', 'Unknown')
                year = ref.get('year', 'N/A')
                confidence = ref.get('confidence', 0.0)
                lines.append(f"  {GRAY}[{i}] {title} ({year}) - Confidence: {confidence:.1%}{RESET}")
        
        # Processing time
        if result.get("processing_time"):
            lines.append(f"\n{GRAY}Processing time: {result['processing_time']:.2f}s{RESET}")
        
        return "\n".join(lines)
    
    def process_query(self, query: str, follow_up: bool = False) -> Dict[str, Any]:
        """Process a single query."""
        # Build context from conversation history if follow-up
        context = None
        if follow_up and self.conversation_history:
            context = {
                "session_id": self.session_id,
                "conversation_history": self.conversation_history[-3:]  # Last 3 exchanges
            }
        
        # Process the query
        result = self.orchestrator.process(
            query=query,
            context=context
        )
        
        # Update conversation history
        self.conversation_history.append({
            "query": query,
            "response": result.get("response", ""),
            "timestamp": datetime.now().isoformat()
        })
        
        return result
    
    def interactive_mode(self):
        """Run in interactive mode with conversation support."""
        print(f"{BOLD}Interactive Mode - Type 'help' for commands, 'exit' to quit{RESET}\n")
        
        while True:
            try:
                # Get user input
                query = input(f"{BOLD}{GREEN}Query> {RESET}").strip()
                
                # Handle special commands
                if not query:
                    continue
                elif query.lower() in ['exit', 'quit', 'q']:
                    print(f"{BLUE}Goodbye!{RESET}")
                    break
                elif query.lower() == 'help':
                    self.show_help()
                    continue
                elif query.lower() == 'clear':
                    self.conversation_history = []
                    print(f"{GREEN}✓ Conversation history cleared{RESET}\n")
                    continue
                elif query.lower() == 'history':
                    self.show_history()
                    continue
                elif query.lower() == 'save':
                    self.save_conversation()
                    continue
                
                # Determine if this is a follow-up
                is_follow_up = len(self.conversation_history) > 0
                if is_follow_up:
                    print(f"{GRAY}(Follow-up question detected){RESET}")
                
                # Process the query
                print(f"{GRAY}Processing...{RESET}")
                result = self.process_query(query, follow_up=is_follow_up)
                
                # Display the response
                print(self.format_response(result))
                print()
                
            except KeyboardInterrupt:
                print(f"\n{BLUE}Interrupted. Type 'exit' to quit.{RESET}\n")
            except Exception as e:
                print(f"{RED}Error: {e}{RESET}\n")
    
    def show_help(self):
        """Show help information."""
        help_text = f"""
{CYAN}━━━ Available Commands ━━━{RESET}
  help     - Show this help message
  clear    - Clear conversation history
  history  - Show conversation history
  save     - Save conversation to file
  exit     - Exit the program

{CYAN}━━━ Query Examples ━━━{RESET}
  • "What are the contraindications for bronchial thermoplasty?"
  • "Show me CPT codes for EBUS procedures"
  • "How many fiducials should be placed for SBRT?"
  • "What about the spacing?" (follow-up question)

{CYAN}━━━ Emergency Queries ━━━{RESET}
  Emergency queries are automatically detected and prioritized:
  • "massive hemoptysis management"
  • "tension pneumothorax needle decompression"
  • "foreign body aspiration protocol"
        """
        print(help_text)
    
    def show_history(self):
        """Show conversation history."""
        if not self.conversation_history:
            print(f"{GRAY}No conversation history yet{RESET}\n")
            return
        
        print(f"\n{CYAN}━━━ Conversation History ━━━{RESET}")
        for i, exchange in enumerate(self.conversation_history, 1):
            timestamp = exchange.get('timestamp', '')[:19]  # Trim microseconds
            print(f"\n{GRAY}[{i}] {timestamp}{RESET}")
            print(f"{BOLD}Q:{RESET} {exchange['query']}")
            response = exchange['response'][:200] + "..." if len(exchange['response']) > 200 else exchange['response']
            print(f"{BOLD}A:{RESET} {response}")
        print()
    
    def save_conversation(self):
        """Save conversation to a JSON file."""
        if not self.conversation_history:
            print(f"{YELLOW}No conversation to save{RESET}\n")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"conversation_{timestamp}.json"
        
        data = {
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "model": os.getenv("IP_GPT5_MODEL", "gpt-4o-mini"),
            "conversation": self.conversation_history
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"{GREEN}✓ Conversation saved to {filename}{RESET}\n")
    
    def single_query_mode(self, query: str):
        """Process a single query and exit."""
        print(f"{GRAY}Processing query...{RESET}")
        result = self.process_query(query, follow_up=False)
        print(self.format_response(result))

def main():
    parser = argparse.ArgumentParser(
        description='Enhanced CLI interface for IP Assist with conversation support'
    )
    parser.add_argument(
        'query',
        nargs='?',
        help='Query to process (if not provided, enters interactive mode)'
    )
    parser.add_argument(
        '--model',
        default=None,
        help='GPT model to use (default: IP_GPT5_MODEL env var or gpt-4o-mini)'
    )
    parser.add_argument(
        '--host',
        default='localhost',
        help='Qdrant host (default: localhost)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=6333,
        help='Qdrant port (default: 6333)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output response as JSON'
    )
    
    args = parser.parse_args()
    
    # Initialize CLI
    cli = EnhancedCLI(
        model=args.model,
        qdrant_host=args.host,
        qdrant_port=args.port
    )
    
    # Process based on mode
    if args.query:
        # Single query mode
        if args.json:
            result = cli.process_query(args.query, follow_up=False)
            print(json.dumps(result, indent=2))
        else:
            cli.single_query_mode(args.query)
    else:
        # Interactive mode
        try:
            cli.interactive_mode()
        except KeyboardInterrupt:
            print(f"\n{BLUE}Goodbye!{RESET}")

if __name__ == "__main__":
    main()