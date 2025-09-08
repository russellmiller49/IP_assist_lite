#!/usr/bin/env python3
"""
Simple CLI interface for IP Assist Lite
Use this while Gradio frontend is being fixed
"""
import sys
import os
sys.path.insert(0, 'src')

from ui.gradio_app import get_orchestrator, process_query
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
import time

console = Console()

def main():
    """Run the CLI interface."""
    console.print(Panel.fit(
        "[bold cyan]IP Assist Lite - CLI Interface[/bold cyan]\n"
        "[dim]Medical Information Retrieval System[/dim]",
        border_style="cyan"
    ))
    
    # Initialize orchestrator
    with console.status("[bold green]Initializing system...") as status:
        orchestrator = get_orchestrator()
        console.print("✅ System ready!\n")
    
    console.print("[yellow]Commands:[/yellow]")
    console.print("  • Type your medical query")
    console.print("  • 'cpt <code>' to search CPT codes")
    console.print("  • 'rerank on/off' to toggle reranker")
    console.print("  • 'topk <n>' to set result count")
    console.print("  • 'stats' to show cache statistics")
    console.print("  • 'quit' to exit\n")
    
    use_reranker = True
    top_k = 5
    
    while True:
        try:
            # Get input
            query = console.input("[bold blue]Query>[/bold blue] ").strip()
            
            if not query:
                continue
            elif query.lower() == 'quit':
                console.print("[red]Goodbye![/red]")
                break
            elif query.lower() == 'stats':
                console.print(Panel(
                    f"Cache Stats:\n"
                    f"• Result cache: {len(getattr(process_query, '_cache', {})._data)} entries\n"
                    f"• Reranker: {'ON' if use_reranker else 'OFF'}\n"
                    f"• Top-K: {top_k}",
                    title="System Statistics",
                    border_style="green"
                ))
                continue
            elif query.lower().startswith('rerank'):
                use_reranker = 'on' in query.lower()
                console.print(f"[green]Reranker: {'ON' if use_reranker else 'OFF'}[/green]")
                continue
            elif query.lower().startswith('topk'):
                try:
                    top_k = int(query.split()[1])
                    console.print(f"[green]Top-K set to: {top_k}[/green]")
                except:
                    console.print("[red]Usage: topk <number>[/red]")
                continue
            elif query.lower().startswith('cpt'):
                # CPT code search
                code = query.split()[1] if len(query.split()) > 1 else ""
                console.print(f"[cyan]Searching CPT code: {code}[/cyan]")
                # Would implement CPT search here
                console.print("[yellow]CPT search not yet implemented in CLI[/yellow]")
                continue
            
            # Process medical query
            with console.status("[bold green]Processing query...") as status:
                start_time = time.time()
                
                # Call the process_query function
                result = process_query(query, use_reranker, top_k)
                
                elapsed = time.time() - start_time
            
            # Display results
            if "⚡ Cached" in result:
                console.print("[yellow]⚡ Cached result[/yellow]")
            
            console.print(Panel(
                Markdown(result),
                title=f"Response ({elapsed:.2f}s)",
                border_style="green",
                padding=(1, 2)
            ))
            
        except KeyboardInterrupt:
            console.print("\n[red]Interrupted[/red]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback
            if console.input("Show traceback? (y/n): ").lower() == 'y':
                traceback.print_exc()

if __name__ == "__main__":
    main()