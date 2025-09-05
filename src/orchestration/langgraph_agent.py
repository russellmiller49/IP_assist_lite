#!/usr/bin/env python3
"""
LangGraph 1.0 orchestration for IP Assist Lite
Implements intelligent query routing, safety checks, and hierarchy-aware retrieval
"""

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
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from retrieval.hybrid_retriever import HybridRetriever, RetrievalResult


# State definition
class IPAssistState(TypedDict):
    """State for the IP Assist graph."""
    query: str
    messages: Annotated[List[BaseMessage], add_messages]
    retrieval_results: List[RetrievalResult]
    is_emergency: bool
    query_type: str  # 'clinical', 'procedure', 'coding', 'emergency', 'safety'
    safety_flags: List[str]
    response: str
    citations: List[Dict[str, Any]]
    confidence_score: float
    needs_review: bool


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
    
    def __init__(self, retriever: Optional[HybridRetriever] = None):
        """Initialize the orchestrator."""
        # Initialize retriever
        if retriever is None:
            self.retriever = HybridRetriever(
                chunks_file="../../data/chunks/chunks.jsonl",
                cpt_index_file="../../data/term_index/cpt_codes.jsonl",
                alias_index_file="../../data/term_index/aliases.jsonl"
            )
        else:
            self.retriever = retriever
        
        # Build the graph
        self.graph = self._build_graph()
        self.app = self.graph.compile()
    
    def _classify_query(self, state: IPAssistState) -> IPAssistState:
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
        
        # Add classification message
        state["messages"].append(
            AIMessage(content=f"Query classified as: {state['query_type']}")
        )
        
        return state
    
    def _retrieve_information(self, state: IPAssistState) -> IPAssistState:
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
        
        state["retrieval_results"] = results
        
        # Add retrieval message
        if results:
            state["messages"].append(
                AIMessage(content=f"Retrieved {len(results)} relevant documents")
            )
        else:
            state["messages"].append(
                AIMessage(content="No relevant documents found")
            )
        
        return state
    
    def _synthesize_response(self, state: IPAssistState) -> IPAssistState:
        """Synthesize response from retrieved information."""
        results = state["retrieval_results"]
        query_type = state["query_type"]
        
        if not results:
            state["response"] = "I couldn't find relevant information for your query. Please try rephrasing or provide more context."
            state["confidence_score"] = 0.0
            return state
        
        # Build response based on query type
        response_parts = []
        citations = []
        
        # Add emergency warning if needed
        if state["is_emergency"]:
            response_parts.append("🚨 **EMERGENCY DETECTED** - Immediate action required\n")
        
        # Process top results
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
            
            # Add to response based on precedence
            if result.authority_tier == "A1":
                response_parts.append(f"**[PAPOIP 2025]** {result.text[:300]}...")
            elif result.authority_tier == "A2":
                response_parts.append(f"**[Practical Guide 2022]** {result.text[:300]}...")
            elif result.authority_tier == "A3":
                response_parts.append(f"**[BACADA 2012]** {result.text[:300]}...")
            else:
                response_parts.append(f"**[{result.doc_id[:20]}...]** {result.text[:300]}...")
        
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
        
        state["confidence_score"] = (top_score + avg_precedence) / 2
        state["response"] = "\n\n".join(response_parts)
        state["citations"] = citations
        
        return state
    
    def _apply_safety_checks(self, state: IPAssistState) -> IPAssistState:
        """Apply final safety checks to the response."""
        validation = SafetyGuard.validate_response(
            state["response"],
            state["safety_flags"]
        )
        
        if validation["has_warnings"]:
            warnings_text = "\n".join(validation["warnings"])
            state["response"] += f"\n\n---\n**Safety Notes:**\n{warnings_text}"
        
        state["needs_review"] = validation["needs_review"]
        
        # Add safety message
        if state["needs_review"]:
            state["messages"].append(
                AIMessage(content="⚠️ Response flagged for review due to safety concerns")
            )
        
        return state
    
    def _route_after_classification(self, state: IPAssistState) -> str:
        """Route to appropriate node based on classification."""
        if state["is_emergency"]:
            return "retrieve"  # Skip directly to retrieval for emergencies
        return "retrieve"
    
    def _route_after_retrieval(self, state: IPAssistState) -> str:
        """Route after retrieval."""
        if not state["retrieval_results"]:
            return "synthesize"  # Will generate "no results" response
        return "synthesize"
    
    def _route_after_synthesis(self, state: IPAssistState) -> str:
        """Route after synthesis."""
        if state["safety_flags"]:
            return "safety_check"
        return "end"
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        # Create the graph
        workflow = StateGraph(IPAssistState)
        
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
        # Initialize state
        initial_state = {
            "query": query,
            "messages": [HumanMessage(content=query)],
            "retrieval_results": [],
            "is_emergency": False,
            "query_type": "",
            "safety_flags": [],
            "response": "",
            "citations": [],
            "confidence_score": 0.0,
            "needs_review": False
        }
        
        # Run the graph
        result = self.app.invoke(initial_state)
        
        # Format output
        output = {
            "query": query,
            "response": result["response"],
            "query_type": result["query_type"],
            "is_emergency": result["is_emergency"],
            "confidence_score": result["confidence_score"],
            "citations": result["citations"],
            "safety_flags": result["safety_flags"],
            "needs_review": result["needs_review"]
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