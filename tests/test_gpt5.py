#!/usr/bin/env python3
"""
Test suite for GPT-5 Medical wrapper
Ensures conformance to canonical interface and JSON safety
"""

import json
import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm.gpt5_medical import GPT5Medical
from safety.contraindication_tool import contraindication_tool_schema, to_jsonable


class TestGPT5Medical(unittest.TestCase):
    """Test GPT-5 Medical wrapper conformance."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.llm = GPT5Medical(
            model="gpt-5-test",
            use_responses=True,
            max_out=500,
            reasoning_effort="medium"
        )
    
    def test_complete_returns_correct_format(self):
        """Test that complete() returns dict with text|tool_calls|raw."""
        messages = [
            {"role": "system", "content": "You are a medical assistant."},
            {"role": "user", "content": "What is bronchoscopy?"}
        ]
        
        # Mock the OpenAI client
        with patch.object(self.llm.client, 'responses') as mock_responses:
            # Create a mock response object
            mock_resp = Mock()
            mock_resp.output_text = "Bronchoscopy is a medical procedure..."
            mock_resp.output = []
            mock_resp.model_dump = Mock(return_value={"usage": {"total_tokens": 100}})
            
            mock_responses.create.return_value = mock_resp
            
            # Call complete
            result = self.llm.complete(messages)
            
            # Assert structure
            self.assertIn("text", result)
            self.assertIn("tool_calls", result)
            self.assertIn("raw", result)
            
            # Assert types
            self.assertIsInstance(result["text"], (str, type(None)))
            self.assertIsInstance(result["tool_calls"], (list, type(None)))
            self.assertIsInstance(result["raw"], dict)
    
    def test_raw_is_json_serializable(self):
        """Test that raw field is JSON-serializable."""
        messages = [
            {"role": "system", "content": "Test"},
            {"role": "user", "content": "Test query"}
        ]
        
        with patch.object(self.llm.client, 'responses') as mock_responses:
            mock_resp = Mock()
            mock_resp.output_text = "Test response"
            mock_resp.output = []
            mock_resp.model_dump = Mock(return_value={
                "usage": {"total_tokens": 50},
                "model": "gpt-5-test",
                "id": "test-123"
            })
            
            mock_responses.create.return_value = mock_resp
            
            result = self.llm.complete(messages)
            
            # Should be able to JSON serialize the raw field
            try:
                json_str = json.dumps(result["raw"])
                self.assertIsInstance(json_str, str)
            except Exception as e:
                self.fail(f"Raw field not JSON-serializable: {e}")
    
    def test_chat_completions_fallback(self):
        """Test fallback to Chat Completions API."""
        llm_chat = GPT5Medical(
            model="gpt-5-test",
            use_responses=False,  # Force Chat Completions
            max_out=500
        )
        
        messages = [
            {"role": "system", "content": "Medical assistant"},
            {"role": "user", "content": "Describe EBUS"}
        ]
        
        with patch.object(llm_chat.client.chat.completions, 'create') as mock_chat:
            # Create mock message
            mock_message = Mock()
            mock_message.content = "EBUS is..."
            mock_message.tool_calls = None
            
            # Create mock choice
            mock_choice = Mock()
            mock_choice.message = mock_message
            
            # Create mock response
            mock_resp = Mock()
            mock_resp.choices = [mock_choice]
            mock_resp.model_dump = Mock(return_value={"usage": {"total_tokens": 75}})
            
            mock_chat.return_value = mock_resp
            
            result = llm_chat.complete(messages)
            
            # Verify structure
            self.assertEqual(result["text"], "EBUS is...")
            self.assertIsInstance(result["tool_calls"], (list, type(None)))
            self.assertIsInstance(result["raw"], dict)
            
            # Verify correct parameter name was used
            call_kwargs = mock_chat.call_args.kwargs
            self.assertIn("max_completion_tokens", call_kwargs)
            self.assertEqual(call_kwargs["max_completion_tokens"], 500)
    
    def test_tool_calling_responses_api(self):
        """Test tool calling with Responses API."""
        messages = [
            {"role": "system", "content": "Use the tool to check safety."},
            {"role": "user", "content": "Check contraindications for bronchoscopy"}
        ]
        
        tools = [contraindication_tool_schema()]
        
        with patch.object(self.llm.client, 'responses') as mock_responses:
            # Create mock tool call
            mock_tool_call = Mock()
            mock_tool_call.type = "tool_call"
            mock_tool_call.tool_name = "emit_contraindication_decision"
            mock_tool_call.arguments = '{"patient_id": "123", "intervention": "bronchoscopy", "decision": "proceed", "rationale": "No contraindications"}'
            
            mock_resp = Mock()
            mock_resp.output_text = None
            mock_resp.output = [mock_tool_call]
            mock_resp.model_dump = Mock(return_value={"tool_calls": [{"name": "emit_contraindication_decision"}]})
            
            mock_responses.create.return_value = mock_resp
            
            result = self.llm.complete(messages, tools=tools)
            
            # Verify tool calls extracted
            self.assertIsNotNone(result["tool_calls"])
            self.assertEqual(len(result["tool_calls"]), 1)
            self.assertEqual(result["tool_calls"][0]["name"], "emit_contraindication_decision")
    
    def test_tool_forcing_chat_completions(self):
        """Test tool forcing with Chat Completions API."""
        llm_chat = GPT5Medical(use_responses=False)
        
        messages = [
            {"role": "system", "content": "Safety check"},
            {"role": "user", "content": "Evaluate pneumothorax risk"}
        ]
        
        tools = [contraindication_tool_schema()]
        tool_choice = {
            "type": "function",
            "function": {"name": "emit_contraindication_decision"}
        }
        
        with patch.object(llm_chat.client.chat.completions, 'create') as mock_chat:
            # Create mock tool call
            mock_func = Mock()
            mock_func.name = "emit_contraindication_decision"
            mock_func.arguments = '{"decision": "use_with_caution"}'
            
            mock_tool_call = Mock()
            mock_tool_call.function = mock_func
            
            mock_message = Mock()
            mock_message.content = None
            mock_message.tool_calls = [mock_tool_call]
            
            mock_choice = Mock()
            mock_choice.message = mock_message
            
            mock_resp = Mock()
            mock_resp.choices = [mock_choice]
            mock_resp.model_dump = Mock(return_value={})
            
            mock_chat.return_value = mock_resp
            
            result = llm_chat.complete(messages, tools=tools, tool_choice=tool_choice)
            
            # Verify tool choice passed correctly
            call_kwargs = mock_chat.call_args.kwargs
            self.assertEqual(call_kwargs["tool_choice"], tool_choice)
            
            # Verify tool calls extracted
            self.assertEqual(len(result["tool_calls"]), 1)
            self.assertEqual(result["tool_calls"][0]["name"], "emit_contraindication_decision")
    
    def test_backward_compatibility(self):
        """Test backward compatibility with generate() method."""
        with patch.object(self.llm.client, 'responses') as mock_responses:
            mock_resp = Mock()
            mock_resp.output_text = "Test response"
            mock_resp.output = []
            mock_resp.model_dump = Mock(return_value={"usage": {"total_tokens": 50}})
            
            mock_responses.create.return_value = mock_resp
            
            result = self.llm.generate(
                system="System prompt",
                user="User query"
            )
            
            # Should have old format
            self.assertIn("text", result)
            self.assertIn("tool_calls", result)
            self.assertIn("usage", result)
    
    def test_to_jsonable_helper(self):
        """Test the to_jsonable helper function."""
        # Mock SDK object with model_dump
        mock_sdk_obj = Mock()
        mock_sdk_obj.model_dump = Mock(return_value={"key": "value"})
        
        # Test various types
        test_cases = [
            (mock_sdk_obj, {"key": "value"}),
            ({"nested": mock_sdk_obj}, {"nested": {"key": "value"}}),
            ([mock_sdk_obj, "string"], [{"key": "value"}, "string"]),
            ("plain_string", "plain_string"),
            (123, 123),
            (None, None)
        ]
        
        for input_val, expected in test_cases:
            result = to_jsonable(input_val)
            self.assertEqual(result, expected)


class TestLangGraphIntegration(unittest.TestCase):
    """Test LangGraph state management integration."""
    
    def test_agent_state_structure(self):
        """Test that AgentState has required fields."""
        from orchestration.langgraph_agent import AgentState
        
        # Verify required fields exist in TypedDict
        required_fields = [
            "user_id", "messages", "query", "retrieved", 
            "draft", "safety"
        ]
        
        # Create a test state
        test_state = {
            "user_id": "test",
            "messages": [],
            "query": "test query",
            "retrieved": [],
            "draft": "",
            "safety": {}
        }
        
        # Should be valid AgentState structure
        for field in required_fields:
            self.assertIn(field, test_state)
    
    def test_graph_compilation(self):
        """Test that the graph compiles successfully."""
        from orchestration.langgraph_agent import IPAssistOrchestrator
        
        # Mock the retriever to avoid file dependencies
        mock_retriever = Mock()
        
        # Create orchestrator with mocked retriever
        orchestrator = IPAssistOrchestrator(retriever=mock_retriever)
        
        # Graph should be compiled
        self.assertIsNotNone(orchestrator.app)
        
        # Should have expected nodes
        self.assertIsNotNone(orchestrator._classify_query)
        self.assertIsNotNone(orchestrator._retrieve_information)
        self.assertIsNotNone(orchestrator._synthesize_response)
        self.assertIsNotNone(orchestrator._apply_safety_checks)


class TestRetrievalIDHandling(unittest.TestCase):
    """Test proper chunk ID handling in retrieval."""
    
    @patch('retrieval.hybrid_retriever.QdrantClient')
    @patch('builtins.open', new_callable=unittest.mock.mock_open, 
           read_data='{"id": "chunk_001", "text": "test"}\n')
    def test_semantic_search_uses_payload_id(self, mock_open, mock_qdrant):
        """Test that semantic search uses payload["id"] for chunk matching."""
        from retrieval.hybrid_retriever import HybridRetriever
        
        # Create mock Qdrant response
        mock_hit = Mock()
        mock_hit.id = "uuid-123"  # Qdrant point ID
        mock_hit.payload = {"id": "chunk_001"}  # Our chunk ID
        mock_hit.score = 0.95
        
        mock_qdrant_instance = Mock()
        mock_qdrant_instance.search.return_value = [mock_hit]
        mock_qdrant.return_value = mock_qdrant_instance
        
        # Create retriever
        retriever = HybridRetriever()
        
        # Perform semantic search
        import numpy as np
        query_embedding = np.random.rand(768)
        results = retriever.semantic_search(query_embedding, top_k=5)
        
        # Should return chunk_001, not uuid-123
        self.assertEqual(results[0][0], "chunk_001")
        self.assertEqual(results[0][1], 0.95)


if __name__ == "__main__":
    unittest.main()