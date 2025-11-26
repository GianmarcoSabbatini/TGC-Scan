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
        """Search cards with Scryfall query syntax"""
        logger.debug(f"Scryfall: Searching cards | query={query} | page={page}")
        self.rate_limiter.wait()
        
        try:
            response = requests.get(
                f"{self.base_url}/cards/search",
                params={'q': query, 'page': page},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                cards = [self._parse_card_data(card) for card in data.get('data', [])]
                logger.info(f"Scryfall: Found {len(cards)} cards for query={query}")
                return cards
            return []
        except Exception as e:
            logger.error(f"Scryfall API error: {e}", exc_info=True)
            return []
    
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
            'card_id': data.get('id'),
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

class PokemonTCGAPI:
    """Pokemon TCG API client"""
    
    def __init__(self):
        self.base_url = config.POKEMON_API_BASE
        logger.debug("PokemonTCGAPI initialized")
        
    def search_card_by_name(self, name: str) -> Optional[Dict]:
        """Search for a Pokemon card by name"""
        logger.debug(f"PokemonTCG: Searching card | name={name}")
        try:
            response = requests.get(
                f"{self.base_url}/cards",
                params={'q': f'name:"{name}"'},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                cards = data.get('data', [])
                if cards:
                    logger.info(f"PokemonTCG: Card found | name={name}")
                    return self._parse_card_data(cards[0])
            logger.debug(f"PokemonTCG: Card not found | name={name}")
            return None
        except Exception as e:
            logger.error(f"Pokemon TCG API error: {e}", exc_info=True)
            return None
    
    def _parse_card_data(self, data: Dict) -> Dict:
        """Parse Pokemon TCG card data to our format"""
        return {
            'tcg': 'pokemon',
            'card_id': data.get('id'),
            'name': data.get('name'),
            'set_code': data.get('set', {}).get('id'),
            'set_name': data.get('set', {}).get('name'),
            'collector_number': data.get('number'),
            'rarity': data.get('rarity'),
            'card_type': ','.join(data.get('types', [])),
            'colors': ','.join(data.get('types', [])),  # Pokemon uses types as colors
            'image_url': data.get('images', {}).get('large'),
            'oracle_text': ' '.join([attack.get('text', '') for attack in data.get('attacks', [])]),
            'artist': data.get('artist'),
            'price_usd': data.get('cardmarket', {}).get('prices', {}).get('averageSellPrice')
        }

class YuGiOhAPI:
    """Yu-Gi-Oh! API client"""
    
    def __init__(self):
        self.base_url = config.YUGIOH_API_BASE
        logger.debug("YuGiOhAPI initialized")
        
    def search_card_by_name(self, name: str) -> Optional[Dict]:
        """Search for a Yu-Gi-Oh! card by name"""
        logger.debug(f"YuGiOh: Searching card | name={name}")
        try:
            response = requests.get(
                f"{self.base_url}/cardinfo.php",
                params={'name': name},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                cards = data.get('data', [])
                if cards:
                    logger.info(f"YuGiOh: Card found | name={name}")
                    return self._parse_card_data(cards[0])
            logger.debug(f"YuGiOh: Card not found | name={name}")
            return None
        except Exception as e:
            logger.error(f"Yu-Gi-Oh! API error: {e}", exc_info=True)
            return None
    
    def _parse_card_data(self, data: Dict) -> Dict:
        """Parse Yu-Gi-Oh! card data to our format"""
        card_images = data.get('card_images', [{}])[0]
        
        return {
            'tcg': 'yugioh',
            'card_id': str(data.get('id')),
            'name': data.get('name'),
            'set_code': data.get('card_sets', [{}])[0].get('set_code', '') if data.get('card_sets') else '',
            'set_name': data.get('card_sets', [{}])[0].get('set_name', '') if data.get('card_sets') else '',
            'rarity': data.get('card_sets', [{}])[0].get('set_rarity', '') if data.get('card_sets') else '',
            'card_type': data.get('type'),
            'colors': data.get('attribute', ''),
            'image_url': card_images.get('image_url'),
            'oracle_text': data.get('desc', ''),
            'price_usd': data.get('card_prices', [{}])[0].get('tcgplayer_price') if data.get('card_prices') else None
        }

class CardAPIManager:
    """Manages all card API integrations"""
    
    def __init__(self):
        self.scryfall = ScryfallAPI()
        self.pokemon = PokemonTCGAPI()
        self.yugioh = YuGiOhAPI()
        
    def search_card(self, name: str, tcg: str = 'mtg') -> Optional[Dict]:
        """Search for a card across different TCG APIs"""
        if tcg == 'mtg':
            return self.scryfall.search_card_by_name(name)
        elif tcg == 'pokemon':
            return self.pokemon.search_card_by_name(name)
        elif tcg == 'yugioh':
            return self.yugioh.search_card_by_name(name)
        return None
    
    def get_card_price(self, card_data: Dict) -> Optional[float]:
        """Extract current price from card data"""
        price = card_data.get('price_usd')
        if price:
            try:
                return float(price)
            except (ValueError, TypeError):
                pass
        return None
