"""
Orchestration flow using LangGraph 1.0 alpha
Implements the retrieval pipeline as a stateful graph
"""
from typing import Dict, List, Any, Optional, TypedDict, Annotated
from dataclasses import dataclass, field
from enum import Enum
import operator

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolExecutor
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field

from src.llm.gpt5_medical import GPT5MedicalGenerator, num_tokens, max_input_budget


class QueryType(str, Enum):
    """Types of queries that require different handling."""
    EMERGENCY = "emergency"
    CODING = "coding"
    CLINICAL = "clinical"
    TRAINING = "training"
    SAFETY = "safety"


class RetrievalState(TypedDict):
    """State for the retrieval graph."""
    # Input
    query: str
    query_type: Optional[QueryType]
    
    # Processing
    query_embedding: Optional[List[float]]
    expanded_terms: List[str]
    
    # Retrieval results
    bm25_results: List[Dict[str, Any]]
    dense_results: List[Dict[str, Any]]
    exact_matches: List[Dict[str, Any]]
    merged_results: List[Dict[str, Any]]
    reranked_results: List[Dict[str, Any]]
    
    # Safety and validation
    safety_flags: List[str]
    contraindications: List[Dict[str, Any]]
    conflicts: List[Dict[str, Any]]
    
    # Emergency handling
    is_emergency: bool
    emergency_info: Optional[Dict[str, Any]]
    
    # Final output
    answer: str
    citations: List[Dict[str, Any]]
    tables: List[Dict[str, Any]]
    temporal_warnings: List[str]
    
    # Metadata
    messages: Annotated[List[BaseMessage], operator.add]
    error: Optional[str]


class IPOrchestrator:
    """Orchestrates the IP retrieval and response pipeline using LangGraph."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the orchestrator with configuration."""
        self.config = config
        self.graph = self._build_graph()
        
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(RetrievalState)
        
        # Add nodes for each processing step
        workflow.add_node("classify_query", self.classify_query)
        workflow.add_node("check_emergency", self.check_emergency)
        workflow.add_node("expand_query", self.expand_query)
        workflow.add_node("retrieve_bm25", self.retrieve_bm25)
        workflow.add_node("retrieve_dense", self.retrieve_dense)
        workflow.add_node("retrieve_exact", self.retrieve_exact_matches)
        workflow.add_node("merge_results", self.merge_results)
        workflow.add_node("rerank", self.rerank_results)
        workflow.add_node("check_safety", self.check_safety)
        workflow.add_node("resolve_conflicts", self.resolve_conflicts)
        workflow.add_node("compose_answer", self.compose_answer)
        workflow.add_node("emergency_response", self.emergency_response)
        
        # Define the flow with conditional edges
        workflow.set_entry_point("classify_query")
        
        # After classification, check for emergency
        workflow.add_edge("classify_query", "check_emergency")
        
        # Emergency branch
        workflow.add_conditional_edges(
            "check_emergency",
            lambda state: "emergency_response" if state["is_emergency"] else "expand_query",
            {
                "emergency_response": "emergency_response",
                "expand_query": "expand_query"
            }
        )
        
        # Emergency response goes straight to answer
        workflow.add_edge("emergency_response", "compose_answer")
        
        # Normal flow: expand query then parallel retrieval
        workflow.add_edge("expand_query", "retrieve_bm25")
        workflow.add_edge("expand_query", "retrieve_dense")
        workflow.add_edge("expand_query", "retrieve_exact")
        
        # All retrieval methods converge at merge
        workflow.add_edge("retrieve_bm25", "merge_results")
        workflow.add_edge("retrieve_dense", "merge_results")
        workflow.add_edge("retrieve_exact", "merge_results")
        
        # Continue processing
        workflow.add_edge("merge_results", "rerank")
        workflow.add_edge("rerank", "check_safety")
        workflow.add_edge("check_safety", "resolve_conflicts")
        workflow.add_edge("resolve_conflicts", "compose_answer")
        
        # End after composing answer
        workflow.add_edge("compose_answer", END)
        
        return workflow.compile()
    
    async def classify_query(self, state: RetrievalState) -> Dict[str, Any]:
        """Classify the query type."""
        query = state["query"].lower()
        
        # Emergency keywords
        if any(term in query for term in ["massive hemoptysis", "emergency", "urgent", "immediate"]):
            query_type = QueryType.EMERGENCY
        # Coding/billing keywords
        elif any(term in query for term in ["cpt", "rvu", "billing", "coding", "reimbursement"]):
            query_type = QueryType.CODING
        # Training keywords
        elif any(term in query for term in ["training", "competency", "fellowship", "education"]):
            query_type = QueryType.TRAINING
        # Safety keywords
        elif any(term in query for term in ["contraindication", "safety", "complication", "risk"]):
            query_type = QueryType.SAFETY
        else:
            query_type = QueryType.CLINICAL
        
        return {"query_type": query_type}
    
    async def check_emergency(self, state: RetrievalState) -> Dict[str, Any]:
        """Check if query is an emergency and needs fast routing."""
        query = state["query"].lower()
        
        emergency_triggers = {
            "massive_hemoptysis": ["massive hemoptysis", ">200 ml", "hemodynamic instability"],
            "foreign_body": ["foreign body aspiration", "fb removal"],
            "tension_pneumothorax": ["tension pneumothorax", "cardiovascular collapse"],
        }
        
        is_emergency = False
        emergency_info = {}
        
        for emergency_type, keywords in emergency_triggers.items():
            if any(keyword in query for keyword in keywords):
                is_emergency = True
                emergency_info = {
                    "type": emergency_type,
                    "priority": "CRITICAL",
                    "max_latency_ms": 500
                }
                break
        
        return {
            "is_emergency": is_emergency,
            "emergency_info": emergency_info
        }
    
    async def expand_query(self, state: RetrievalState) -> Dict[str, Any]:
        """Expand query with aliases and related terms."""
        query = state["query"]
        expanded_terms = [query]
        
        # Common IP term expansions
        expansions = {
            "ebus": ["endobronchial ultrasound", "EBUS"],
            "enb": ["electromagnetic navigation bronchoscopy", "ENB"],
            "blvr": ["bronchoscopic lung volume reduction", "BLVR", "valves"],
            "pdt": ["photodynamic therapy", "PDT"],
            "rp-ebus": ["radial probe endobronchial ultrasound", "radial probe EBUS"],
        }
        
        query_lower = query.lower()
        for abbrev, full_terms in expansions.items():
            if abbrev in query_lower:
                expanded_terms.extend(full_terms)
        
        return {"expanded_terms": list(set(expanded_terms))}
    
    async def retrieve_bm25(self, state: RetrievalState) -> Dict[str, Any]:
        """BM25 sparse retrieval."""
        # Placeholder for BM25 retrieval
        # In production, this would call the actual BM25 index
        results = []
        return {"bm25_results": results}
    
    async def retrieve_dense(self, state: RetrievalState) -> Dict[str, Any]:
        """Dense vector retrieval using MedCPT."""
        # Placeholder for dense retrieval
        # In production, this would query Qdrant
        results = []
        return {"dense_results": results}
    
    async def retrieve_exact_matches(self, state: RetrievalState) -> Dict[str, Any]:
        """Exact match retrieval for CPT codes and device names."""
        query = state["query"]
        exact_matches = []
        
        # Check for CPT codes
        import re
        cpt_pattern = r'\b(\d{5})\b'
        cpt_matches = re.findall(cpt_pattern, query)
        
        # In production, lookup CPT codes in term index
        for cpt in cpt_matches:
            # Placeholder for actual CPT lookup
            exact_matches.append({
                "type": "cpt",
                "code": cpt,
                "score": 1.0
            })
        
        return {"exact_matches": exact_matches}
    
    async def merge_results(self, state: RetrievalState) -> Dict[str, Any]:
        """Merge results from different retrieval methods."""
        all_results = []
        
        # Combine all retrieval results
        all_results.extend(state.get("bm25_results", []))
        all_results.extend(state.get("dense_results", []))
        all_results.extend(state.get("exact_matches", []))
        
        # De-duplicate and merge scores
        # Placeholder for actual merging logic
        merged = all_results[:50]  # Top 50 candidates
        
        return {"merged_results": merged}
    
    async def rerank_results(self, state: RetrievalState) -> Dict[str, Any]:
        """Rerank using cross-encoder."""
        # Placeholder for cross-encoder reranking
        # In production, use MedCPT cross-encoder or similar
        reranked = state.get("merged_results", [])[:10]
        return {"reranked_results": reranked}
    
    async def check_safety(self, state: RetrievalState) -> Dict[str, Any]:
        """Check for safety issues and contraindications."""
        safety_flags = []
        contraindications = []
        
        # Check query for safety-critical procedures
        query = state["query"].lower()
        
        if "sems" in query and "benign" in query:
            safety_flags.append("SEMS_BENIGN_WARNING")
            contraindications.append({
                "condition": "benign stenosis",
                "procedure": "SEMS",
                "severity": "absolute"
            })
        
        return {
            "safety_flags": safety_flags,
            "contraindications": contraindications
        }
    
    async def resolve_conflicts(self, state: RetrievalState) -> Dict[str, Any]:
        """Resolve conflicts between sources."""
        # Placeholder for conflict resolution
        # Would implement hierarchy-aware resolution
        conflicts = []
        return {"conflicts": conflicts}
    
    async def compose_answer(self, state: RetrievalState) -> Dict[str, Any]:
        """Compose the final answer."""
        answer_parts = []
        
        # Add emergency warning if applicable
        if state.get("is_emergency"):
            answer_parts.append("⚠️ EMERGENCY SITUATION DETECTED")
        
        # Add safety warnings
        if state.get("safety_flags"):
            answer_parts.append(f"Safety Warnings: {', '.join(state['safety_flags'])}")
        
        # Placeholder for actual answer composition
        answer_parts.append("Based on the evidence...")
        
        return {
            "answer": "\n\n".join(answer_parts),
            "citations": []
        }
    
    async def emergency_response(self, state: RetrievalState) -> Dict[str, Any]:
        """Fast path for emergency queries."""
        emergency_info = state.get("emergency_info", {})
        emergency_type = emergency_info.get("type", "unknown")
        
        # Predefined emergency responses
        emergency_protocols = {
            "massive_hemoptysis": """
IMMEDIATE ACTIONS:
1. Place patient in lateral decubitus position (bleeding side down)
2. Secure airway - consider intubation with large ETT (≥8.0)
3. Initiate bronchoscopy for localization
4. Consider balloon tamponade for temporary control
5. Prepare for bronchial artery embolization
6. ICU admission required
""",
            "foreign_body": """
IMMEDIATE ACTIONS:
1. Maintain spontaneous ventilation if possible
2. Prepare rigid bronchoscopy setup
3. Have optical forceps ready
4. Ensure backup surgical team available
5. Consider general anesthesia with muscle relaxation
""",
            "tension_pneumothorax": """
IMMEDIATE ACTIONS:
1. Needle decompression 2nd ICS MCL
2. Prepare for chest tube insertion
3. 100% oxygen
4. IV access and fluid resuscitation
5. Monitor for re-expansion pulmonary edema
"""
        }
        
        answer = emergency_protocols.get(emergency_type, "Emergency protocol not found")
        
        return {
            "answer": f"🚨 EMERGENCY RESPONSE - {emergency_type.upper()}\n\n{answer}",
            "citations": [],
            "safety_flags": ["EMERGENCY_PROTOCOL_ACTIVATED"]
        }
    
    async def process(self, query: str) -> Dict[str, Any]:
        """Process a query through the graph."""
        initial_state = {
            "query": query,
            "messages": [HumanMessage(content=query)],
            "query_type": None,
            "is_emergency": False,
            "bm25_results": [],
            "dense_results": [],
            "exact_matches": [],
            "merged_results": [],
            "reranked_results": [],
            "safety_flags": [],
            "contraindications": [],
            "conflicts": [],
            "expanded_terms": [],
            "answer": "",
            "citations": [],
            "tables": [],
            "temporal_warnings": []
        }
        
        # Run the graph
        final_state = await self.graph.ainvoke(initial_state)
        
        # Extract key outputs
        return {
            "answer": final_state.get("answer", ""),
            "citations": final_state.get("citations", []),
            "safety_flags": final_state.get("safety_flags", []),
            "is_emergency": final_state.get("is_emergency", False),
            "query_type": final_state.get("query_type", "")
        }


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def test_orchestrator():
        config = {}
        orchestrator = IPOrchestrator(config)
        
        # Test emergency query
        result = await orchestrator.process("Patient with massive hemoptysis >300ml, hemodynamically unstable")
        print("Emergency Query Result:")
        print(result["answer"])
        print()
        
        # Test normal query
        result = await orchestrator.process("What is the CPT code for bronchoscopy with EBUS?")
        print("Normal Query Result:")
        print(result["answer"])
    
    asyncio.run(test_orchestrator())


def context_budget_filter(docs, reserved_for_question: int = 2000, max_out: int = 8000):
    """Keep best-ranked docs while staying under the dynamic prompt budget.""" 
    budget = max_input_budget(max_out) - reserved_for_question
    total, kept = 0, []
    for d in docs:
        tk = num_tokens(getattr(d, "page_content", ""))
        if total + tk > budget:
            break
        total += tk
        kept.append(d)
    return kept


def build_gpt5_answer_node():
    llm = GPT5MedicalGenerator(model=os.getenv("GPT5_MODEL", "gpt-5"),
                               max_output=8000,
                               reasoning_effort="medium",
                               verbosity="medium")
    def _answer(state: "GraphState") -> "GraphState":
        # fit retrieved docs to dynamic budget
        trimmed = context_budget_filter(state.retrieved_docs, max_out=llm.max_out)
        context = format_context(trimmed)  # assumes your helper exists
        system = (
            "You are an expert interventional pulmonology assistant. "
            "Use only the provided authoritative context. "
            "Cite sources as [A1-PAPOIP-2025], [A2-Practical-Guide], etc. "
            "If uncertain, state so explicitly."
        )
        user = f"Context:\n{context}\n\nQuestion: {state.question}"
        out = llm.generate(system=system, user=user)
        state.answer = out.get("text", "")
        state.llm_usage = out.get("usage", {})
        return state
    return _answer

workflow.add_node("generate_answer", build_gpt5_answer_node())
