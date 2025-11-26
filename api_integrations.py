"""
TCG Scan - API Integrations
Handles communication with external card databases and price APIs
"""
import requests
import time
from typing import Dict, List, Optional
import config
from logger import get_logger, PerformanceLogger

# Initialize logger for this module
logger = get_logger('api')

class RateLimiter:
    """Simple rate limiter for API calls"""
    def __init__(self, calls_per_second: int):
        self.calls_per_second = calls_per_second
        self.last_call = 0
        
    def wait(self):
        """Wait if necessary to respect rate limit"""
        now = time.time()
        time_since_last = now - self.last_call
        min_interval = 1.0 / self.calls_per_second
        
        if time_since_last < min_interval:
            time.sleep(min_interval - time_since_last)
        
        self.last_call = time.time()

class ScryfallAPI:
    """Scryfall API client for Magic: The Gathering cards"""
    
    def __init__(self):
        self.base_url = config.SCRYFALL_API_BASE
        self.rate_limiter = RateLimiter(config.SCRYFALL_RATE_LIMIT)
        logger.debug("ScryfallAPI initialized")
        
    def search_card_by_name(self, name: str) -> Optional[Dict]:
        """Search for a card by exact or fuzzy name"""
        logger.debug(f"Scryfall: Searching card by name | name={name}")
        self.rate_limiter.wait()
        
        try:
            response = requests.get(
                f"{self.base_url}/cards/named",
                params={'fuzzy': name},
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Scryfall: Card found | name={name}")
                return self._parse_card_data(response.json())
            logger.debug(f"Scryfall: Card not found | name={name} | status={response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Scryfall API error: {e}", exc_info=True)
            return None
    
    def get_card_by_set_and_number(self, set_code: str, collector_number: str) -> Optional[Dict]:
        """Get specific card by set and collector number"""
        logger.debug(f"Scryfall: Getting card | set={set_code} | number={collector_number}")
        self.rate_limiter.wait()
        
        try:
            response = requests.get(
                f"{self.base_url}/cards/{set_code}/{collector_number}",
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Scryfall: Card retrieved | set={set_code} | number={collector_number}")
                return self._parse_card_data(response.json())
            return None
        except Exception as e:
            logger.error(f"Scryfall API error: {e}", exc_info=True)
            return None
    
    def search_cards(self, query: str, page: int = 1) -> List[Dict]:
        """Search cards with Scryfall query syntax - returns all pages"""
        logger.debug(f"Scryfall: Searching cards | query={query}")
        
        all_cards = []
        has_more = True
        current_page = 1
        
        while has_more:
            self.rate_limiter.wait()
            
            try:
                response = requests.get(
                    f"{self.base_url}/cards/search",
                    params={'q': query, 'page': current_page},
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    cards = [self._parse_card_data(card) for card in data.get('data', [])]
                    all_cards.extend(cards)
                    has_more = data.get('has_more', False)
                    current_page += 1
                    logger.debug(f"Scryfall: Page {current_page - 1} fetched | cards_so_far={len(all_cards)}")
                else:
                    has_more = False
            except Exception as e:
                logger.error(f"Scryfall API error: {e}", exc_info=True)
                has_more = False
        
        logger.info(f"Scryfall: Found {len(all_cards)} total cards for query={query}")
        return all_cards
    
    def get_set_card_count(self, set_code: str) -> int:
        """Get the total number of cards in a set"""
        logger.debug(f"Scryfall: Getting set card count | set={set_code}")
        self.rate_limiter.wait()
        
        try:
            response = requests.get(
                f"{self.base_url}/sets/{set_code}",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                count = data.get('card_count', 0)
                logger.info(f"Scryfall: Set {set_code} has {count} cards")
                return count
            return 0
        except Exception as e:
            logger.error(f"Scryfall API error: {e}", exc_info=True)
            return 0
    
    def _parse_card_data(self, data: Dict) -> Dict:
        """Parse Scryfall card data to our format"""
        # Handle double-faced cards
        image_url = data.get('image_uris', {}).get('normal')
        if not image_url and 'card_faces' in data:
            image_url = data['card_faces'][0].get('image_uris', {}).get('normal')
        
        colors = data.get('colors', [])
        if not colors and 'card_faces' in data:
            colors = data['card_faces'][0].get('colors', [])
        
        return {
            'tcg': 'mtg',
            'id': data.get('id'),
            'card_id': data.get('id'),
            'scryfall_id': data.get('id'),
            'name': data.get('name'),
            'set_code': data.get('set'),
            'set_name': data.get('set_name'),
            'collector_number': data.get('collector_number'),
            'rarity': data.get('rarity'),
            'card_type': data.get('type_line'),
            'colors': ','.join(colors),
            'mana_cost': data.get('mana_cost', ''),
            'image_url': image_url,
            'oracle_text': data.get('oracle_text', ''),
            'flavor_text': data.get('flavor_text', ''),
            'artist': data.get('artist'),
            'is_foil': data.get('foil', False),
            'language': data.get('lang', 'en'),
            'price_usd': data.get('prices', {}).get('usd'),
            'price_usd_foil': data.get('prices', {}).get('usd_foil'),
            'price_eur': data.get('prices', {}).get('eur'),
            'price_eur_foil': data.get('prices', {}).get('eur_foil')
        }

class CardAPIManager:
    """Manages Magic: The Gathering card API"""
    
    def __init__(self):
        self.scryfall = ScryfallAPI()
        
    def search_card(self, name: str) -> Optional[Dict]:
        """Search for a MTG card"""
        return self.scryfall.search_card_by_name(name)
    
    def get_card_price(self, card_data: Dict) -> Optional[float]:
        """Extract current price from card data"""
        price = card_data.get('price_usd')
        if price:
            try:
                return float(price)
            except (ValueError, TypeError):
                pass
        return None
