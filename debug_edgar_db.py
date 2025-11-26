
import sys
import os
import io
from api_integrations import CardAPIManager
from card_recognition import download_and_hash_card_image
from database import init_db, get_db, Card

# Fix encoding for print
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def test_edgar_db_insert():
    print("Testing Edgar Markov DB insertion...")
    api_manager = CardAPIManager()
    
    try:
        # 1. Search
        print("1. Searching...")
        card_data = api_manager.search_card("Edgar Markov", "mtg")
        
        if not card_data:
            print("ERROR: Card not found")
            return
            
        # 2. Hash
        print("2. Hashing...")
        image_hash = download_and_hash_card_image(card_data)
        if image_hash:
            card_data['image_hash'] = image_hash
            
        # 3. Insert
        print("3. Inserting into DB...")
        # init_db() # Assuming already init
        db = get_db()
        try:
            # Check existing
            existing = db.query(Card).filter(Card.card_id == card_data['card_id']).first()
            if existing:
                print("Card already exists in DB. Deleting for test...")
                db.delete(existing)
                db.commit()
            
            card = Card(**card_data)
            db.add(card)
            db.commit()
            print("Success! Card inserted into DB.")
            
        except Exception as e:
            print(f"DB ERROR: {e}")
            db.rollback()
            raise e
        finally:
            db.close()
            
    except Exception as e:
        print(f"CRASH: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_edgar_db_insert()
