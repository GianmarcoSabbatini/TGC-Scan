"""Script per aggiornare i prezzi delle carte esistenti"""
from database import get_db, Card, PriceHistory
from api_integrations import ScryfallAPI
import time

def update_mtg_prices():
    api = ScryfallAPI()
    db = get_db()
    
    cards = db.query(Card).filter(Card.tcg == 'mtg').all()
    print(f'Found {len(cards)} MTG cards to update prices')
    
    updated = 0
    for card in cards:
        # Check if has price already
        existing = db.query(PriceHistory).filter(PriceHistory.card_id == card.id).first()
        if existing:
            print(f'  {card.name}: already has price EUR {existing.price}')
            continue
        
        # Fetch from API
        try:
            result = api.search_card_by_name(card.name)
            time.sleep(0.1)  # Rate limit
            
            if result and result.get('price_eur'):
                price_record = PriceHistory(
                    card_id=card.id,
                    price=float(result['price_eur']),
                    price_source='scryfall',
                    currency='EUR'
                )
                db.add(price_record)
                db.commit()
                print(f'  {card.name}: EUR {result["price_eur"]}')
                updated += 1
            elif result and result.get('price_usd'):
                price_record = PriceHistory(
                    card_id=card.id,
                    price=float(result['price_usd']),
                    price_source='scryfall',
                    currency='USD'
                )
                db.add(price_record)
                db.commit()
                print(f'  {card.name}: USD {result["price_usd"]}')
                updated += 1
            else:
                print(f'  {card.name}: no price found in API response')
        except Exception as e:
            print(f'  {card.name}: error {e}')
    
    db.close()
    print(f'\nDone! Updated {updated} card prices.')

if __name__ == '__main__':
    update_mtg_prices()
