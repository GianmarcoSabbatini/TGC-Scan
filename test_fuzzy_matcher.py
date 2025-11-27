"""
Test script for the Fuzzy Card Matcher
Run this to verify OCR error correction is working.
"""
import os
import sys

# Suppress verbose logging during test
os.environ['LOG_LEVEL'] = 'WARNING'

from fuzzy_matcher import FuzzyCardMatcher

def test_fuzzy_matcher():
    print("Initializing fuzzy matcher...")
    fm = FuzzyCardMatcher()
    
    print()
    print("=" * 60)
    print("FUZZY MATCHER TEST - OCR Error Correction")
    print("=" * 60)
    
    # Test cases: (OCR text with errors, expected correct name)
    tests = [
        # Common OCR errors (character substitution)
        ("Llghtning Bolt", "Lightning Bolt"),
        ("Counterspei", "Counterspell"),
        ("Sol Rlng", "Sol Ring"),
        ("Dark Rltual", "Dark Ritual"),
        ("Brainstrom", "Brainstorm"),
        
        # Missing characters
        ("Black Lotu", "Black Lotus"),
        ("Force of Wil", "Force of Will"),
        ("Birds of Paradis", "Birds of Paradise"),
        
        # Exact matches (should work too)
        ("Thoughtseize", "Thoughtseize"),
        ("Tarmogoyf", "Tarmogoyf"),
        ("Liliana of the Veil", "Liliana of the Veil"),
        
        # Truncated names (with ..)
        ("Jace the Mind Sculpt..", "Jace, the Mind Sculptor"),
        ("Emrakul the Aeons T..", "Emrakul, the Aeons Torn"),
        
        # Extra characters
        ("Lightning Bolt1", "Lightning Bolt"),
        ("Counterspell@", "Counterspell"),
    ]
    
    passed = 0
    failed = 0
    
    print()
    for ocr_text, expected in tests:
        result = fm.search(ocr_text)
        
        # Check if match is correct (case-insensitive)
        is_match = result and result.lower() == expected.lower()
        status = "OK" if is_match else "FAIL"
        
        if is_match:
            passed += 1
        else:
            failed += 1
        
        print(f'[{status:4}] "{ocr_text}" -> "{result or "NOT FOUND"}"')
        if result and not is_match:
            print(f'       Expected: "{expected}"')
    
    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    # Test confidence scores
    print()
    print("Confidence Score Examples:")
    print("-" * 40)
    
    confidence_tests = [
        "Lightning Bolt",      # Exact match
        "Llghtning Bolt",      # 1 error
        "Lightnng Blt",        # Multiple errors
    ]
    
    for text in confidence_tests:
        result, confidence = fm.search_with_confidence(text)
        print(f'  "{text}"')
        print(f'    -> "{result}" (confidence: {confidence:.2f})')
        print()
    
    return failed == 0


if __name__ == "__main__":
    success = test_fuzzy_matcher()
    sys.exit(0 if success else 1)
