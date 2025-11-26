"""Test collection API"""
import requests
import json

r = requests.get('http://localhost:5000/api/collection')
data = r.json()

print(f'Cards: {len(data["cards"])}')
print(f'Total cards (with qty): {data.get("total_cards", "N/A")}')
print()

for c in data['cards']:
    name = c.get('name', 'Unknown')
    price_eur = c.get('price_eur')
    price_usd = c.get('price_usd')
    qty = c.get('quantity', 1)
    set_name = c.get('set_name', 'Unknown')
    
    price_str = f"EUR {price_eur}" if price_eur else (f"USD {price_usd}" if price_usd else "NO PRICE")
    print(f'  {name} ({set_name}): {price_str} - qty: {qty}')

# Show raw JSON for first card
print("\n--- First card raw JSON ---")
if data['cards']:
    print(json.dumps(data['cards'][0], indent=2))
