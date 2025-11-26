"""Verify prices are working"""
from database import get_db, Card, PriceHistory

db = get_db()

# Get all cards with prices
cards = db.query(Card).all()
print(f"Total cards: {len(cards)}")

for card in cards:
    prices = db.query(PriceHistory).filter(PriceHistory.card_id == card.id).order_by(PriceHistory.recorded_at.desc()).all()
    if prices:
        latest = prices[0]
        print(f"  {card.name}: {latest.currency} {latest.price}")
    else:
        print(f"  {card.name}: NO PRICE")

# Check what to_dict returns
print("\n--- Card.to_dict() output ---")
for card in cards[:2]:
    d = card.to_dict()
    print(f"  {d['name']}: price_eur={d.get('price_eur')}, price_usd={d.get('price_usd')}")

db.close()
