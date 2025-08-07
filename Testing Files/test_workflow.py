#!/usr/bin/env python3
"""
Test script to verify the complete RAG workflow
"""

import os
import time
import tempfile
from agents.mcp_coordinator import MCPCoordinatorAgent

def test_complete_workflow():
    """Test the complete upload and query workflow"""
    
    print("=== Testing Complete RAG Workflow ===")
    
    # Initialize coordinator
    print("1. Initializing coordinator...")
    coordinator = MCPCoordinatorAgent()
    
    # Clear existing data
    print("2. Clearing existing data...")
    coordinator.retrieval_agent.clear_collection()
    
    # Create test document
    print("3. Creating test document...")
    test_content = """
    Store Inventory Analysis Report
    
    This document contains analysis of store inventory data including:
    - Product categories and their performance
    - Sales trends over the past quarter
    - Inventory turnover rates
    - Recommendations for stock optimization
    
    Key findings:
    - Electronics category shows highest sales volume
    - Clothing inventory has slow turnover
    - Seasonal items need better forecasting
    - Overall inventory efficiency is 78%
    """
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(test_content)
        test_file = f.name
    
    print(f"   Created: {test_file}")
    
    try:
        # Test document processing
        print("4. Processing document...")
        result = coordinator.process_document(test_file)
        print(f"   Processing started: {result}")
        
        # Wait for processing to complete
        print("5. Waiting for processing to complete...")
        time.sleep(3)
        
        # Check collection status
        collection_info = coordinator.retrieval_agent.get_collection_info()
        print(f"   Collection info: {collection_info}")
        
        if collection_info['count'] == 0:
            print("   ERROR: No documents were indexed!")
            return False
        
        # Test queries
        print("6. Testing queries...")
        
        test_queries = [
            "What is the inventory efficiency?",
            "Which category has the highest sales?",
            "What are the key findings?",
            "Tell me about clothing inventory"
        ]
        
        for query in test_queries:
            print(f"\n   Query: {query}")
            
            # Test retrieval
            retrieval_result = coordinator.retrieval_agent.retrieve_context(query)
            print(f"   Retrieved {len(retrieval_result.get('top_chunks', []))} chunks")
            
            if retrieval_result.get('top_chunks'):
                # Test LLM response
                llm_result = coordinator.llm_agent.generate_response(
                    query=query,
                    context_chunks=retrieval_result['top_chunks'],
                    chunk_metadata=retrieval_result.get('chunk_metadata', [])
                )
                
                if llm_result.get('status') == 'success':
                    print(f"   Answer: {llm_result['answer'][:100]}...")
                else:
                    print(f"   LLM Error: {llm_result.get('error')}")
            else:
                print("   No relevant context found")
        
        print("\n=== Workflow Test Complete ===")
        return True
        
    finally:
        # Clean up
        if os.path.exists(test_file):
            os.remove(test_file)
            print(f"Cleaned up: {test_file}")

if __name__ == "__main__":
    success = test_complete_workflow()
    if success:
        print("✅ Workflow test PASSED")
    else:
        print("❌ Workflow test FAILED")