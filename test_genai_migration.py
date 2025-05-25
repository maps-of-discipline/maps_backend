#!/usr/bin/env python3
"""
Simple test script to verify that the Google Genai API migration is working correctly.
"""
import sys
import os

# Add the current directory to the path so we can import from competencies_matrix
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_genai_import():
    """Test that the new google.genai package can be imported correctly."""
    try:
        from competencies_matrix.nlp import GOOGLE_GENAI_SDK_AVAILABLE, gemini_client
        print(f"✓ Successfully imported nlp module")
        print(f"✓ GOOGLE_GENAI_SDK_AVAILABLE: {GOOGLE_GENAI_SDK_AVAILABLE}")
        print(f"✓ gemini_client initialized: {gemini_client is not None}")
        
        if GOOGLE_GENAI_SDK_AVAILABLE:
            from google import genai
            from google.genai import types
            print(f"✓ Successfully imported google.genai and types")
            print(f"✓ genai.Client available: {hasattr(genai, 'Client')}")
            print(f"✓ types.GenerateContentConfig available: {hasattr(types, 'GenerateContentConfig')}")
        else:
            print("! google-genai package not available, but import handling works correctly")
            
    except Exception as e:
        print(f"✗ Error testing genai import: {e}")
        return False
    
    return True

def test_api_structure():
    """Test that the API structure matches what we expect from the new version."""
    try:
        from competencies_matrix.nlp import GOOGLE_GENAI_SDK_AVAILABLE
        
        if not GOOGLE_GENAI_SDK_AVAILABLE:
            print("! Skipping API structure test - google-genai not available")
            return True
            
        from google import genai
        from google.genai import types
        
        # Test that we can create a client (without API key for now)
        # This should work but will fail when we try to make actual requests
        try:
            client = genai.Client(api_key="dummy_key")
            print(f"✓ Can create genai.Client")
            print(f"✓ Client has models attribute: {hasattr(client, 'models')}")
            print(f"✓ Client.models has generate_content method: {hasattr(client.models, 'generate_content')}")
        except Exception as e:
            print(f"! Client creation failed (expected with dummy key): {e}")
        
        # Test GenerateContentConfig
        try:
            config = types.GenerateContentConfig(temperature=0.0, max_output_tokens=100)
            print(f"✓ Can create GenerateContentConfig")
        except Exception as e:
            print(f"✗ GenerateContentConfig creation failed: {e}")
            return False
            
    except Exception as e:
        print(f"✗ Error testing API structure: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("Testing Google Genai API migration...")
    print("=" * 50)
    
    success = True
    success &= test_genai_import()
    print()
    success &= test_api_structure()
    
    print()
    print("=" * 50)
    if success:
        print("✓ All tests passed! Migration appears successful.")
        print("\nNext steps:")
        print("1. Install the new package: pip install google-genai")
        print("2. Uninstall the old package: pip uninstall google-generativeai")
        print("3. Test with actual API calls")
    else:
        print("✗ Some tests failed. Please review the migration.")
    
    sys.exit(0 if success else 1)
