#!/usr/bin/env python3
"""
LangGraph 1.0 orchestration for IP Assist Lite
Implements intelligent query routing, safety checks, and hierarchy-aware retrieval
"""
from __future__ import annotations

import sys
import json
import re
from typing import Dict, Any, List, Optional, TypedDict, Annotated, Literal
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph.graph import StateGraph, START, END

from retrieval.hybrid_retriever import HybridRetriever, RetrievalResult
from llm.gpt5_medical import GPT5Medical


# State definition (LangGraph 1.0 canonical)
class AgentState(TypedDict):
    """Canonical state for the IP Assist graph."""
    user_id: str
    messages: List[Dict[str, str]]  # chat history
    query: str
    retrieved: List[Dict[str, Any]]
    draft: str
    safety: Dict[str, Any]
    # Additional fields for IP Assist specific needs
    is_emergency: bool
    query_type: str  # 'clinical', 'procedure', 'coding', 'emergency', 'safety'
    safety_flags: List[str]
    citations: List[Dict[str, Any]]
    confidence_score: float
    needs_review: bool
    # LLM telemetry
    llm_model_used: Optional[str]
    llm_warning_banner: Optional[str]
    llm_error: Optional[str]


@dataclass
class SafetyGuard:
    """Safety checks for medical information."""
    
    CRITICAL_PATTERNS = {
        'dosage': r'\d+\s*(?:mg|mcg|ml|cc|units?|IU)\b',
        'pediatric': r'\b(?:child|children|pediatric|infant|neonate)\b',
        'pregnancy': r'\b(?:pregnan|gestation|fetal|maternal)\b',
        'contraindication': r'\b(?:contraindic|absolute(?:ly)?\s+contraindic|must not|never)\b',
        'allergy': r'\b(?:allerg|anaphyla|hypersensitiv)\b',
        'emergency': r'\b(?:emergency|urgent|stat|immediate|life.?threatening)\b'
    }
    
    @classmethod
    def check_query(cls, query: str) -> List[str]:
        """Check query for safety-critical terms."""
        flags = []
        query_lower = query.lower()
        
        for flag_type, pattern in cls.CRITICAL_PATTERNS.items():
            if re.search(pattern, query_lower):
                flags.append(flag_type)
        
        return flags
    
    @classmethod
    def validate_response(cls, response: str, flags: List[str]) -> Dict[str, Any]:
        """Validate response for safety concerns."""
        warnings = []
        
        # Check for dose/setting information
        if 'dosage' in flags:
            if not re.search(r'verify|confirm|consult|check', response.lower()):
                warnings.append("⚠️ Dose information provided - verify with official guidelines")
        
        # Check for pediatric considerations
        if 'pediatric' in flags:
            if not re.search(r'pediatric|child|weight.?based|age.?appropriate', response.lower()):
                warnings.append("⚠️ Pediatric query - ensure age-appropriate information")
        
        # Check for contraindications
        if 'contraindication' in flags:
            if not re.search(r'contraindic|caution|avoid|risk', response.lower()):
                warnings.append("⚠️ Safety check - contraindication information may be incomplete")
        
        return {
            'has_warnings': len(warnings) > 0,
            'warnings': warnings,
            'needs_review': len(warnings) > 2
        }


class IPAssistOrchestrator:
    """LangGraph orchestration for IP Assist Lite."""
    
    def __init__(self, retriever: Optional[HybridRetriever] = None, model: str = "gpt-5-mini"):
        """Initialize the orchestrator.
        
        Args:
            retriever: Optional HybridRetriever instance
            model: OpenAI model to use (gpt-5-nano, gpt-5-mini, gpt-5, etc.)
        """
        # Initialize retriever
        if retriever is None:
            self.retriever = HybridRetriever(
                chunks_file=Path(__file__).parent.parent.parent / "data" / "chunks" / "chunks.jsonl",
                cpt_index_file=Path(__file__).parent.parent.parent / "data" / "term_index" / "cpt_codes.jsonl",
                alias_index_file=Path(__file__).parent.parent.parent / "data" / "term_index" / "aliases.jsonl"
            )
        else:
            self.retriever = retriever
        
        # Store model for dynamic switching
        self.current_model = model
        
        # Initialize LLM wrapper
        self.llm = GPT5Medical(
            model=model,
            max_out=1500,
            # Use Responses API for GPT-5 family; Chat for others
            use_responses=str(model or "").startswith("gpt-5")
        )
        
        # Build the graph
        self.graph = self._build_graph()
        self.app = self.graph.compile()
    
    def set_model(self, model: str):
        """Switch to a different model dynamically.
        
        Args:
            model: Model name (e.g., 'gpt-4o-mini', 'gpt-4o', 'o1-mini', 'o1-preview')
        """
        if model != self.current_model:
            self.current_model = model
            self.llm = GPT5Medical(
                model=model,
                max_out=1500,
                use_responses=str(model or "").startswith("gpt-5")
            )
    
    def _classify_query(self, state: AgentState) -> AgentState:
        """Classify the query type and check for emergencies."""
        query = state["query"]
        
        # Check for emergency
        state["is_emergency"] = self.retriever.detect_emergency(query)
        
        # Check safety flags
        state["safety_flags"] = SafetyGuard.check_query(query)
        
        # Classify query type
        query_lower = query.lower()
        
        if state["is_emergency"]:
            state["query_type"] = "emergency"
        elif re.search(r'\b(?:cpt|code|bill|reimburs|rvu)\b', query_lower):
            state["query_type"] = "coding"
        elif re.search(r'\b(?:procedure|technique|step|how to|perform)\b', query_lower):
            state["query_type"] = "procedure"
        elif any(flag in state["safety_flags"] for flag in ['contraindication', 'allergy', 'pregnancy']):
            state["query_type"] = "safety"
        else:
            state["query_type"] = "clinical"
        
        # Add classification message (canonical format)
        state["messages"].append(
            {"role": "assistant", "content": f"Query classified as: {state['query_type']}"}
        )
        
        return state
    
    def _retrieve_information(self, state: AgentState) -> AgentState:
        """Retrieve relevant information based on query type."""
        query = state["query"]
        query_type = state["query_type"]
        
        # Set retrieval parameters based on query type
        filters = {}
        top_k = 5
        
        if query_type == "emergency":
            # For emergencies, prioritize high authority and recent guidelines
            filters = {"authority_tier": "A1"}
            top_k = 10
        elif query_type == "coding":
            # For coding, look for tables and exact matches
            filters = {"has_table": True}
            top_k = 5
        elif query_type == "safety":
            # For safety, look for contraindications
            filters = {"has_contraindication": True}
            top_k = 8
        
        # Perform retrieval
        results = self.retriever.retrieve(
            query=query,
            top_k=top_k,
            use_reranker=True,
            filters=filters if query_type in ["emergency", "coding", "safety"] else None
        )
        
        # Store in canonical 'retrieved' field
        state["retrieved"] = [r.__dict__ for r in results] if results else []
        
        # Add retrieval message (canonical format)
        if results:
            state["messages"].append(
                {"role": "assistant", "content": f"Retrieved {len(results)} relevant documents"}
            )
        else:
            state["messages"].append(
                {"role": "assistant", "content": "No relevant documents found"}
            )
        
        return state
    
    def _synthesize_response(self, state: AgentState) -> AgentState:
        """Synthesize response from retrieved information."""
        # Convert back from dict format
        from types import SimpleNamespace
        results = [SimpleNamespace(**r) for r in state["retrieved"]]
        query_type = state["query_type"]
        
        if not results:
            state["draft"] = "I couldn't find relevant information for your query. Please try rephrasing or provide more context."
            state["confidence_score"] = 0.0
            return state
        
        # Build response based on query type
        response_parts = []
        citations = []
        
        # Add emergency warning if needed
        if state["is_emergency"]:
            response_parts.append("🚨 **EMERGENCY DETECTED** - Immediate action required\n")
        
        # Collect context from top results
        context_parts = []
        for i, result in enumerate(results[:3], 1):
            # Build citation
            citation = {
                "doc_id": result.doc_id,
                "section": result.section_title,
                "authority": result.authority_tier,
                "evidence": result.evidence_level,
                "year": result.year,
                "score": result.score
            }
            citations.append(citation)
            
            # Add to context for LLM
            source_label = {
                "A1": "PAPOIP 2025",
                "A2": "Practical Guide 2022",
                "A3": "BACADA 2012"
            }.get(result.authority_tier, result.doc_id[:30])
            
            context_parts.append(f"[{source_label}]: {result.text}")
        
        # Use LLM to synthesize response
        if context_parts:
            context = "\n\n".join(context_parts)
            prompt = f"""Based on the following authoritative medical sources, provide a comprehensive answer to: {state['query']}

Sources:
{context}

Please synthesize this information into a clear, professional response. Prioritize information from higher authority sources (A1 > A2 > A3 > A4). Include specific details like doses, contraindications, and techniques when mentioned."""
            
            try:
                # Send a clean, minimal context (avoid noisy assistant history)
                synth_messages = [
                    {"role": "system", "content": (
                        "You are an expert interventional pulmonology assistant. "
                        "Synthesize a clinically useful answer using only the retrieved Sources. "
                        "Cite sources inline as [A1], [A2], [A3] where relevant. "
                        "Be concise but complete; include key complications/contraindications/doses when applicable."
                    )}
                ]
                llm_response = self.llm.generate_response(prompt, synth_messages)
                response_parts.append(llm_response)
                # Capture LLM telemetry
                state["llm_model_used"] = getattr(self.llm, "last_used_model", self.current_model)
                banner = getattr(self.llm, "last_warning_banner", None)
                if banner:
                    state["llm_warning_banner"] = banner
            except Exception as e:
                # Fallback: Show the raw context if LLM fails
                response_parts.append("**Retrieved Information:**\n")
                for i, part in enumerate(context_parts[:3], 1):
                    response_parts.append(f"\n{i}. {part[:500]}...")
                # Surface error details for UI/metadata
                state["llm_error"] = str(e)
                banner = getattr(self.llm, "last_warning_banner", None)
                if banner:
                    state["llm_warning_banner"] = banner
        else:
            response_parts.append("No relevant information found for your query.")
        
        # Add safety warnings if needed
        if state["safety_flags"]:
            response_parts.append("\n⚠️ **Safety Considerations:**")
            for flag in state["safety_flags"]:
                if flag == "dosage":
                    response_parts.append("• Verify all doses with official guidelines")
                elif flag == "pediatric":
                    response_parts.append("• Ensure pediatric-appropriate dosing and techniques")
                elif flag == "contraindication":
                    response_parts.append("• Review all contraindications before proceeding")
        
        # Calculate confidence based on result quality
        top_score = results[0].score if results else 0
        avg_precedence = sum(r.precedence_score for r in results[:3]) / min(3, len(results))
        
        # Clamp confidence to [0,1]
        conf = (top_score + avg_precedence) / 2
        state["confidence_score"] = max(0.0, min(1.0, conf))
        # Store in canonical 'draft' field
        state["draft"] = "\n\n".join(response_parts)
        state["citations"] = citations
        
        return state
    
    def _apply_safety_checks(self, state: AgentState) -> AgentState:
        """Apply final safety checks to the response."""
        validation = SafetyGuard.validate_response(
            state["draft"],
            state["safety_flags"]
        )
        
        if validation["has_warnings"]:
            warnings_text = "\n".join(validation["warnings"])
            state["draft"] += f"\n\n---\n**Safety Notes:**\n{warnings_text}"
        
        # Store safety information in canonical field
        state["safety"] = validation
        
        state["needs_review"] = validation["needs_review"]
        
        # Add safety message (canonical format)
        if state["needs_review"]:
            state["messages"].append(
                {"role": "assistant", "content": "⚠️ Response flagged for review due to safety concerns"}
            )
        
        return state
    
    def _route_after_classification(self, state: AgentState) -> str:
        """Route to appropriate node based on classification."""
        if state["is_emergency"]:
            return "retrieve"  # Skip directly to retrieval for emergencies
        return "retrieve"
    
    def _route_after_retrieval(self, state: AgentState) -> str:
        """Route after retrieval."""
        if not state["retrieved"]:
            return "synthesize"  # Will generate "no results" response
        return "synthesize"
    
    def _route_after_synthesis(self, state: AgentState) -> str:
        """Route after synthesis."""
        if state["safety_flags"]:
            return "safety_check"
        return "end"
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        # Create the graph (canonical LangGraph 1.0)
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("classify", self._classify_query)
        workflow.add_node("retrieve", self._retrieve_information)
        workflow.add_node("synthesize", self._synthesize_response)
        workflow.add_node("safety_check", self._apply_safety_checks)
        
        # Add edges
        workflow.add_edge(START, "classify")
        workflow.add_conditional_edges(
            "classify",
            self._route_after_classification,
            {"retrieve": "retrieve"}
        )
        workflow.add_conditional_edges(
            "retrieve",
            self._route_after_retrieval,
            {"synthesize": "synthesize"}
        )
        workflow.add_conditional_edges(
            "synthesize",
            self._route_after_synthesis,
            {"safety_check": "safety_check", "end": END}
        )
        workflow.add_edge("safety_check", END)
        
        return workflow
    
    def process_query(self, query: str) -> Dict[str, Any]:
        """Process a query through the orchestration graph."""
        # Initialize state (canonical format)
        initial_state = {
            "user_id": "default",  # Can be passed as parameter
            "messages": [{"role": "user", "content": query}],
            "query": query,
            "retrieved": [],
            "draft": "",
            "safety": {},
            # IP Assist specific
            "is_emergency": False,
            "query_type": "",
            "safety_flags": [],
            "citations": [],
            "confidence_score": 0.0,
            "needs_review": False
        }
        
        # Run the graph
        result = self.app.invoke(initial_state)
        
        # Format output
        output = {
            "query": query,
            "response": result["draft"],  # Use draft field
            "query_type": result["query_type"],
            "is_emergency": result["is_emergency"],
            "confidence_score": result["confidence_score"],
            "citations": result["citations"],
            "safety_flags": result["safety_flags"],
            "needs_review": result["needs_review"],
            # LLM telemetry
            "model_requested": self.current_model,
            "model_used": result.get("llm_model_used"),
            "llm_warning": result.get("llm_warning_banner"),
            "llm_error": result.get("llm_error"),
        }
        
        return output


def main():
    """Test the orchestrator."""
    orchestrator = IPAssistOrchestrator()
    
    # Test queries
    test_queries = [
        "What are the contraindications for bronchoscopy?",
        "Massive hemoptysis management protocol",
        "CPT code for EBUS-TBNA",
        "Pediatric bronchoscopy dosing for lidocaine",
        "How to place fiducial markers for SBRT?"
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        
        result = orchestrator.process_query(query)
        
        print(f"\n📊 Query Type: {result['query_type']}")
        if result['is_emergency']:
            print("🚨 EMERGENCY DETECTED")
        print(f"🎯 Confidence: {result['confidence_score']:.2%}")
        
        if result['safety_flags']:
            print(f"⚠️ Safety Flags: {', '.join(result['safety_flags'])}")
        
        print(f"\n📝 Response:")
        print(result['response'])
        
        if result['citations']:
            print(f"\n📚 Sources:")
            for i, cite in enumerate(result['citations'], 1):
                print(f"  [{i}] {cite['doc_id']} ({cite['authority']}/{cite['evidence']}, {cite['year']})")
        
        if result['needs_review']:
            print("\n⚠️ This response has been flagged for review")


if __name__ == "__main__":
    main()
