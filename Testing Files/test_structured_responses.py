#!/usr/bin/env python3
"""
Test script to verify the new structured response format
"""

import os
import time
import tempfile
from agents.mcp_coordinator import MCPCoordinatorAgent

def test_structured_responses():
    """Test the new structured response format"""
    
    print("=== Testing Structured Response Format ===")
    
    # Initialize coordinator
    print("1. Initializing coordinator...")
    coordinator = MCPCoordinatorAgent()
    
    # Clear existing data
    print("2. Clearing existing data...")
    coordinator.retrieval_agent.clear_collection()
    
    # Create test document with structured data
    print("3. Creating test document with structured data...")
    test_content = """
    Sales Performance Report Q4 2024
    
    Monthly Sales Data:
    January: $45,000
    February: $52,000
    March: $48,000
    April: $61,000
    May: $58,000
    June: $67,000
    July: $82,000 (highest)
    August: $75,000
    September: $69,000
    October: $71,000
    November: $64,000
    December: $59,000
    
    Product Categories:
    - Electronics: 35% of total sales
    - Clothing: 28% of total sales  
    - Home & Garden: 22% of total sales
    - Books & Media: 15% of total sales
    
    Key Performance Indicators:
    - Average monthly sales: $62,583
    - Growth rate: 12% year-over-year
    - Customer satisfaction: 4.2/5.0
    - Return rate: 3.1%
    
    Top Performing Products:
    1. Smartphone Pro Max - $15,000 revenue
    2. Wireless Headphones - $12,500 revenue
    3. Smart Watch Series 5 - $11,200 revenue
    4. Laptop Gaming Edition - $9,800 revenue
    5. Tablet Ultra - $8,900 revenue
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
        
        # Test structured queries
        print("6. Testing structured response queries...")
        
        test_queries = [
            "What was the highest sales month and what was the amount?",
            "Show me the product category breakdown",
            "What are the key performance indicators?",
            "List the top 5 performing products with their revenue",
            "Create a summary of the sales performance"
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n   Query {i}: {query}")
            print("   " + "="*50)
            
            # Test retrieval
            retrieval_result = coordinator.retrieval_agent.retrieve_context(query)
            
            if retrieval_result.get('top_chunks'):
                # Test LLM response with new structured format
                llm_result = coordinator.llm_agent.generate_response(
                    query=query,
                    context_chunks=retrieval_result['top_chunks'],
                    chunk_metadata=retrieval_result.get('chunk_metadata', [])
                )
                
                if llm_result.get('status') == 'success':
                    print(f"   Response Type: {llm_result.get('response_type')}")
                    print(f"   Sources Used: {llm_result.get('sources_used')}")
                    print("\n   STRUCTURED RESPONSE:")
                    print("   " + "-"*40)
                    # Print first 300 characters to see the structure
                    response_preview = llm_result['answer'][:500] + "..." if len(llm_result['answer']) > 500 else llm_result['answer']
                    print("   " + response_preview.replace('\n', '\n   '))
                    print("   " + "-"*40)
                else:
                    print(f"   LLM Error: {llm_result.get('error')}")
            else:
                print("   No relevant context found")
        
        print("\n=== Structured Response Test Complete ===")
        return True
        
    finally:
        # Clean up
        if os.path.exists(test_file):
            os.remove(test_file)
            print(f"Cleaned up: {test_file}")

if __name__ == "__main__":
    success = test_structured_responses()
    if success:
        print("✅ Structured Response test PASSED")
        print("\nYour responses should now be:")
        print("• Well-structured with clear sections")
        print("• Easy to read with bullet points")
        print("• Include tables when appropriate")
        print("• Have clear headings and organization")
    else:
        print("❌ Structured Response test FAILED")