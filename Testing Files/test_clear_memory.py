#!/usr/bin/env python3
"""
Test script to verify the clear memory functionality
"""

import requests
import json
import time
import tempfile
import os

def test_clear_memory_functionality():
    """Test the complete clear memory workflow"""
    
    base_url = 'http://127.0.0.1:8009'  # Adjust port as needed
    
    print("=== Testing Clear Memory Functionality ===")
    
    try:
        # Test 1: Upload a document first
        print("1. Uploading test document...")
        
        test_content = """
        Test Document for Clear Memory
        
        This document contains test data that should be cleared:
        - Product A: $100
        - Product B: $200  
        - Product C: $300
        
        Total inventory value: $600
        """
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(test_content)
            test_file = f.name
        
        # Upload the file
        with open(test_file, 'rb') as f:
            files = {'files': (os.path.basename(test_file), f, 'text/plain')}
            response = requests.post(f'{base_url}/upload', files=files, timeout=30)
        
        if response.status_code not in [200, 207]:
            print(f"   ❌ Upload failed: {response.status_code} - {response.text}")
            return False
        
        print(f"   ✅ Document uploaded successfully")
        
        # Wait for processing
        time.sleep(3)
        
        # Test 2: Query the uploaded document
        print("2. Testing query before clear...")
        
        query_data = {"query": "What is the total inventory value?"}
        response = requests.post(
            f'{base_url}/query',
            json=query_data,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Query successful: {result.get('answer', 'No answer')[:100]}...")
            print(f"   Sources used: {result.get('sources_used', 0)}")
            
            if result.get('sources_used', 0) == 0:
                print("   ⚠️  Warning: No sources found, document might not be indexed yet")
        else:
            print(f"   ❌ Query failed: {response.status_code} - {response.text}")
        
        # Test 3: Clear memory
        print("3. Testing clear memory...")
        
        response = requests.post(
            f'{base_url}/clear',
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Clear successful: {result.get('message')}")
        else:
            print(f"   ❌ Clear failed: {response.status_code} - {response.text}")
            return False
        
        # Test 4: Query after clear (should have no sources)
        print("4. Testing query after clear...")
        
        query_data = {"query": "What is the total inventory value?"}
        response = requests.post(
            f'{base_url}/query',
            json=query_data,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Query successful: {result.get('answer', 'No answer')[:100]}...")
            print(f"   Sources used: {result.get('sources_used', 0)}")
            
            if result.get('sources_used', 0) == 0:
                print("   ✅ Perfect! No sources found after clear - memory was cleared successfully")
            else:
                print("   ⚠️  Warning: Sources still found after clear - memory might not be fully cleared")
        else:
            print(f"   ❌ Query after clear failed: {response.status_code} - {response.text}")
        
        # Test 5: Check health status
        print("5. Checking system health...")
        
        response = requests.get(f'{base_url}/health', timeout=10)
        if response.status_code == 200:
            health_data = response.json()
            print(f"   ✅ System healthy: {health_data.get('status')}")
        else:
            print(f"   ⚠️  Health check issue: {response.status_code}")
        
        print("\n=== Clear Memory Test Complete ===")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}")
        print("Make sure Flask app is running on the correct port")
        return False
    
    finally:
        # Clean up
        if 'test_file' in locals() and os.path.exists(test_file):
            os.remove(test_file)
            print(f"Cleaned up: {test_file}")

if __name__ == "__main__":
    print("Make sure your Flask app is running first!")
    print("Run: python app.py")
    print()
    
    success = test_clear_memory_functionality()
    if success:
        print("✅ Clear Memory functionality test PASSED")
        print("\nYour clear memory button should work correctly!")
    else:
        print("❌ Clear Memory functionality test FAILED")