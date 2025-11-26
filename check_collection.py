
import sys
import os
from database import get_db, ScannedCard, Card

import config

def check_collection():
    print(f"Using Database: {config.DATABASE_PATH}")
    print("Checking ScannedCard table...")
    db = get_db()
    try:
        cards = db.query(ScannedCard).all()
        print(f"Total scanned cards: {len(cards)}")
        for card in cards:
            print(f"ID: {card.id}, Card ID: {card.card_id}, Path: {card.image_path}")
            if card.card:
                print(f"  -> Linked to: {card.card.name}")
            else:
                print("  -> ORPHANED (No linked Card)")
                
        # Try manual insertion
        print("\nAttempting manual insertion...")
        try:
            card = db.query(Card).first()
            if card:
                print(f"Found card ID {card.id} to link")
                scanned = ScannedCard(
                    card_id=card.id,
                    image_path=card.image_url,
                    confidence_score=1.0,
                    match_type='manual_test',
                    condition='NM',
                    quantity=1
                )
                db.add(scanned)
                db.commit()
                print(f"Successfully inserted ScannedCard ID: {scanned.id}")
            else:
                print("No cards in DB to link to.")
        except Exception as e:
            print(f"Manual insertion failed: {e}")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_collection()
