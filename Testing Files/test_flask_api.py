#!/usr/bin/env python3
"""
Test script to verify Flask API endpoints
"""

import requests
import json
import time
import tempfile
import os

def test_flask_api():
    """Test the Flask API endpoints"""
    
    base_url = 'http://127.0.0.1:8009'
    
    print("=== Testing Flask API ===")
    
    try:
        # Test health endpoint
        print("1. Testing health endpoint...")
        response = requests.get(f'{base_url}/health', timeout=10)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            health_data = response.json()
            print(f"   System status: {health_data.get('status')}")
        else:
            print(f"   Error: {response.text}")
            return False
        
        # Clear existing documents
        print("2. Clearing existing documents...")
        response = requests.post(f'{base_url}/clear', timeout=10)
        print(f"   Clear status: {response.status_code}")
        
        # Create test file
        print("3. Creating test file...")
        test_content = """
        Store Inventory Analysis Report
        
        This document contains detailed analysis of our store inventory:
        
        Key Metrics:
        - Total inventory value: $2.5M
        - Inventory turnover: 4.2x annually
        - Out-of-stock rate: 3.2%
        - Overstock items: 15% of total SKUs
        
        Category Performance:
        - Electronics: 35% of sales, high demand
        - Clothing: 28% of sales, seasonal variations
        - Home goods: 22% of sales, steady demand
        - Books: 15% of sales, declining trend
        
        Recommendations:
        1. Increase electronics inventory by 20%
        2. Implement better forecasting for clothing
        3. Reduce book inventory gradually
        4. Focus on fast-moving home goods
        """
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(test_content)
            test_file = f.name
        
        print(f"   Created: {test_file}")
        
        # Test file upload
        print("4. Testing file upload...")
        with open(test_file, 'rb') as f:
            files = {'files': (os.path.basename(test_file), f, 'text/plain')}
            response = requests.post(f'{base_url}/upload', files=files, timeout=30)
        
        print(f"   Upload status: {response.status_code}")
        if response.status_code in [200, 207]:
            upload_data = response.json()
            print(f"   Upload result: {upload_data.get('message')}")
            print(f"   Files processed: {len(upload_data.get('uploaded_files', []))}")
        else:
            print(f"   Upload error: {response.text}")
            return False
        
        # Wait for processing
        print("5. Waiting for document processing...")
        time.sleep(5)
        
        # Test queries
        print("6. Testing queries...")
        
        test_queries = [
            "What is the total inventory value?",
            "Which category has the highest sales percentage?",
            "What are the recommendations?",
            "What is the inventory turnover rate?"
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n   Query {i}: {query}")
            
            query_data = {
                "query": query,
                "search_k": 3
            }
            
            response = requests.post(
                f'{base_url}/query',
                json=query_data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"   Answer: {result.get('answer', 'No answer')[:100]}...")
                print(f"   Sources used: {result.get('sources_used', 0)}")
                print(f"   Collection size: {result.get('collection_size', 0)}")
            else:
                print(f"   Query error: {response.text}")
        
        print("\n=== Flask API Test Complete ===")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"Connection error: {e}")
        print("Make sure Flask app is running: python app.py")
        return False
    
    finally:
        # Clean up
        if 'test_file' in locals() and os.path.exists(test_file):
            os.remove(test_file)
            print(f"Cleaned up: {test_file}")

if __name__ == "__main__":
    success = test_flask_api()
    if success:
        print("✅ Flask API test PASSED")
    else:
        print("❌ Flask API test FAILED")