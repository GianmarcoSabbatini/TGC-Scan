
import sys
import os
from api_integrations import CardAPIManager

def test_edgar_import():
    print("Testing Edgar Markov import...")
    api_manager = CardAPIManager()
    
    try:
        # Search for Edgar Markov
        print("Searching for 'Edgar Markov'...")
        card_data = api_manager.search_card("Edgar Markov", "mtg")
        
        if card_data:
            print("Success! Card data found:")
            print(card_data)
        else:
            print("Card not found (returned None)")
            
    except Exception as e:
        print(f"ERROR CAUGHT: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_edgar_import()
