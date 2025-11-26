
import sys
import os
import io
from api_integrations import CardAPIManager
from card_recognition import download_and_hash_card_image

# Fix encoding for print
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def test_edgar_full():
    print("Testing Edgar Markov full import process...")
    api_manager = CardAPIManager()
    
    try:
        # 1. Search
        print("1. Searching for 'Edgar Markov'...")
        card_data = api_manager.search_card("Edgar Markov", "mtg")
        
        if not card_data:
            print("ERROR: Card not found")
            return
            
        print(f"Success! Found: {card_data['name']}")
        print(f"Image URL: {card_data.get('image_url')}")
        
        # 2. Download and Hash
        print("2. Downloading and hashing image...")
        image_hash = download_and_hash_card_image(card_data)
        
        if image_hash:
            print(f"Success! Hash: {image_hash}")
        else:
            print("WARNING: Image hash is None (this is not a crash, but might be unexpected)")
            
    except Exception as e:
        print(f"CRASH: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_edgar_full()
