#!/usr/bin/env python3
"""
Test script to simulate the upload and query workflow
"""

import os
import tempfile
from agents.mcp_coordinator import MCPCoordinatorAgent

def test_upload_query_workflow():
    """Test the complete upload and query workflow like your Flask app"""
    
    print("=== Testing Upload and Query Workflow ===")
    
    # Initialize coordinator (like Flask app startup)
    print("1. Initializing system...")
    coordinator = MCPCoordinatorAgent()
    
    # Clear existing data
    print("2. Clearing existing documents...")
    coordinator.retrieval_agent.clear_collection()
    
    # Simulate CSV upload with store inventory data
    print("3. Simulating CSV upload...")
    csv_content = """Product,Category,Stock,Sales,Price
iPhone 14,Electronics,50,120,999
Samsung TV,Electronics,25,80,799
Nike Shoes,Clothing,100,200,129
Adidas Shirt,Clothing,150,180,49
Coffee Maker,Home,30,45,89
Blender,Home,20,35,79
Python Book,Books,40,15,39
JavaScript Guide,Books,35,12,45"""
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        csv_file = f.name
    
    print(f"   Created CSV file: {csv_file}")
    
    try:
        # Process the uploaded file (like Flask upload endpoint)
        print("4. Processing uploaded file...")
        result = coordinator.process_document(csv_file)
        print(f"   Processing result: {result}")
        
        # Wait for processing
        import time
        time.sleep(3)
        
        # Check if document was indexed
        collection_info = coordinator.retrieval_agent.get_collection_info()
        print(f"   Collection after upload: {collection_info}")
        
        if collection_info['count'] == 0:
            print("   ❌ ERROR: Document was not indexed!")
            return False
        
        # Test queries (like Flask query endpoint)
        print("5. Testing queries on uploaded data...")
        
        test_queries = [
            "What products are in the Electronics category?",
            "Which product has the highest sales?",
            "What is the price of Nike Shoes?",
            "How many books are in stock?",
            "What categories are available?"
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n   Query {i}: {query}")
            
            # Step 1: Get context (like Flask query endpoint)
            retrieval_result = coordinator.retrieval_agent.retrieve_context(
                query=query,
                k=5,
                similarity_threshold=0.7
            )
            
            if retrieval_result.get("status") == "error":
                print(f"   ❌ Retrieval failed: {retrieval_result.get('error')}")
                continue
            
            context_chunks = retrieval_result.get("top_chunks", [])
            chunk_metadata = retrieval_result.get("chunk_metadata", [])
            
            print(f"   Retrieved {len(context_chunks)} chunks")
            
            if not context_chunks:
                print("   ⚠️  No relevant context found")
                continue
            
            # Step 2: Generate response (like Flask query endpoint)
            llm_result = coordinator.llm_agent.generate_response(
                query=query,
                context_chunks=context_chunks,
                chunk_metadata=chunk_metadata,
            )
            
            if llm_result.get("status") == "error":
                print(f"   ❌ LLM failed: {llm_result.get('error')}")
                continue
            
            answer = llm_result.get("answer", "No answer generated")
            print(f"   ✅ Answer: {answer[:150]}...")
            print(f"   Sources used: {len(context_chunks)}")
        
        print("\n=== Upload and Query Test Complete ===")
        return True
        
    finally:
        # Clean up
        if os.path.exists(csv_file):
            os.remove(csv_file)
            print(f"Cleaned up: {csv_file}")

if __name__ == "__main__":
    success = test_upload_query_workflow()
    if success:
        print("✅ Upload and Query workflow PASSED")
        print("\nYour system is working correctly!")
        print("The issue might be with Flask app startup or port conflicts.")
    else:
        print("❌ Upload and Query workflow FAILED")