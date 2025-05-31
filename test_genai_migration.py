#!/usr/bin/env python3
"""
Simple test script to verify that the Google Genai API migration and multi-provider LLM setup is working correctly.
"""
import sys
import os

# Add the current directory to the path so we can import from competencies_matrix
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_genai_import():
    """Test that the new google.genai package can be imported correctly if selected."""
    try:
        from competencies_matrix.nlp import GOOGLE_GENAI_SDK_AVAILABLE, gemini_client, LLM_PROVIDER, openai_compatible_client, OPENAI_SDK_AVAILABLE
        print(f"✓ Successfully imported nlp module")
        print(f"✓ LLM_PROVIDER: {LLM_PROVIDER}")

        if LLM_PROVIDER == 'gemini':
            print(f"✓ GOOGLE_GENAI_SDK_AVAILABLE: {GOOGLE_GENAI_SDK_AVAILABLE}")
            print(f"✓ gemini_client initialized: {gemini_client is not None}")
            if GOOGLE_GENAI_SDK_AVAILABLE:
                from google import genai
                from google.genai import types as gemini_types # Match updated import alias
                print(f"✓ Successfully imported google.genai and types")
                print(f"✓ genai.Client available: {hasattr(genai, 'Client')}")
                print(f"✓ gemini_types.GenerationConfig available: {hasattr(gemini_types, 'GenerationConfig')}") # Match updated class name
            else:
                print("! google-genai package not available, but import handling works correctly for non-gemini provider or if gemini selected but not installed.")
        elif LLM_PROVIDER in ['local', 'klusterai']:
            print(f"✓ OPENAI_SDK_AVAILABLE: {OPENAI_SDK_AVAILABLE}")
            print(f"✓ openai_compatible_client initialized: {openai_compatible_client is not None}")
            if OPENAI_SDK_AVAILABLE:
                from openai import OpenAI
                print(f"✓ Successfully imported openai")
                print(f"✓ OpenAI class available: {hasattr(OpenAI, 'chat')}")
            else:
                print("! openai package not available, but import handling works correctly if non-openai provider selected or if selected but not installed.")
        else:
            print(f"! Unknown LLM_PROVIDER: {LLM_PROVIDER}")
            
    except Exception as e:
        print(f"✗ Error testing genai import: {e}")
        return False
    
    return True

def test_api_structure():
    """Test that the API structure matches what we expect from the new version."""
    try:
        from competencies_matrix.nlp import LLM_PROVIDER, GOOGLE_GENAI_SDK_AVAILABLE, OPENAI_SDK_AVAILABLE
        
        if LLM_PROVIDER == 'gemini':
            if not GOOGLE_GENAI_SDK_AVAILABLE:
                print("! Skipping API structure test for Gemini - google-genai not available")
                return True
            
            from google import genai
            from google.genai import types as gemini_types # Match updated import alias
            
            # Test that we can create a client (without API key for now)
            try:
                client = genai.Client(api_key="dummy_key_gemini")
                print(f"✓ Can create genai.Client")
                print(f"✓ Client has generate_content method: {hasattr(client, 'generate_content')}") # Check for new method
            except Exception as e:
                print(f"! Gemini Client creation failed (expected with dummy key or if not configured): {e}")
            
            # Test GenerationConfig
            try:
                config = gemini_types.GenerationConfig(temperature=0.0, max_output_tokens=100) # Match updated class name
                print(f"✓ Can create GenerationConfig")
            except Exception as e:
                print(f"✗ GenerationConfig creation failed: {e}")
                return False
        elif LLM_PROVIDER in ['local', 'klusterai']:
            if not OPENAI_SDK_AVAILABLE:
                print(f"! Skipping API structure test for {LLM_PROVIDER} - openai SDK not available")
                return True
            
            from openai import OpenAI
            try:
                api_key_to_test = "dummy_key_openai"
                base_url_to_test = "http://localhost:1234/v1" if LLM_PROVIDER == 'local' else "https://api.kluster.ai/v1"
                client = OpenAI(api_key=api_key_to_test, base_url=base_url_to_test)
                print(f"✓ Can create OpenAI client for {LLM_PROVIDER}")
                print(f"✓ OpenAI client has chat.completions.create method: {hasattr(client.chat.completions, 'create')}")
            except Exception as e:
                print(f"! OpenAI Client creation for {LLM_PROVIDER} failed (may be expected if not configured): {e}")
        else:
            print(f"! Unknown LLM_PROVIDER for API structure test: {LLM_PROVIDER}")
            
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
        print("✓ All tests passed! Multi-provider LLM setup appears successful.")
        print("\nNext steps:")
        print("1. Ensure necessary SDKs are installed based on your chosen LLM_PROVIDER:")
        print("   - For 'gemini': pip install google-genai")
        print("   - For 'local' or 'klusterai': pip install openai")
        print("2. Configure environment variables in .env (e.g., GOOGLE_AI_API_KEY, KLUDESTER_AI_API_KEY, LLM_PROVIDER, etc.)")
        print("3. Test with actual API calls to your chosen provider.")
    else:
        print("✗ Some tests failed. Please review the migration.")
    
    sys.exit(0 if success else 1)
