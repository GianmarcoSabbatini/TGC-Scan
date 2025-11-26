
import sys
import os
from database import get_db, Card

def check_edgar_in_db():
    print("Checking if Edgar Markov is in DB...")
    db = get_db()
    try:
        card = db.query(Card).filter(Card.name == "Edgar Markov").first()
        if card:
            print(f"FOUND: {card.name} (ID: {card.id})")
            print(f"Set: {card.set_name}")
            print(f"Image URL: {card.image_url}")
        else:
            print("NOT FOUND")
    finally:
        db.close()

if __name__ == "__main__":
    check_edgar_in_db()
