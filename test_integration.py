"""
Quick test of CardRecognitionEngine integration with fuzzy matcher.
"""
import os
os.environ['LOG_LEVEL'] = 'WARNING'

print("Testing card recognition engine integration...")

from card_recognition import CardRecognitionEngine

print("[OK] CardRecognitionEngine imported successfully")

engine = CardRecognitionEngine()
print("[OK] Engine initialized")

if engine.fuzzy_matcher:
    print("[OK] Fuzzy matcher: ENABLED")
    
    # Test search with OCR error
    print()
    print("Testing search_card_by_name with OCR errors...")
    
    test_cases = [
        "Llghtning Bolt",  # OCR error
        "Counterspei",     # OCR error
        "Black Lotus",     # Correct name
    ]
    
    for test_name in test_cases:
        result = engine.search_card_by_name(test_name)
        if result:
            print(f"  '{test_name}' -> Found: {result.get('name')}")
        else:
            print(f"  '{test_name}' -> Not found")
else:
    print("[WARNING] Fuzzy matcher: DISABLED")

print()
print("Integration test complete!")
