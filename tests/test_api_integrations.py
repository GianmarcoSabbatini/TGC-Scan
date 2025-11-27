"""
TCG Scan - API Integration Tests
Tests for external API clients (Scryfall, Pokemon TCG, Yu-Gi-Oh)
"""
import pytest
from unittest.mock import patch, MagicMock
import requests


class TestRateLimiter:
    """Tests for the rate limiter"""
    
    def test_rate_limiter_basic(self):
        """Test basic rate limiter functionality"""
        from api_integrations import RateLimiter
        import time
        
        limiter = RateLimiter(calls_per_second=10)
        
        start = time.time()
        limiter.wait()
        first_call = time.time()
        limiter.wait()
        second_call = time.time()
        
        # Second call should have some delay
        assert second_call >= first_call + 0.1 - 0.01  # Allow small margin
        
    def test_rate_limiter_respects_limit(self):
        """Test that rate limiter respects the calls per second limit"""
        from api_integrations import RateLimiter
        import time
        
        limiter = RateLimiter(calls_per_second=5)  # 0.2 seconds between calls
        
        start = time.time()
        for _ in range(3):
            limiter.wait()
        end = time.time()
        
        # Should take at least 0.4 seconds for 3 calls
        assert end - start >= 0.35


class TestScryfallAPI:
    """Tests for Scryfall API client"""
    
    def test_search_card_by_name_success(self):
        """Test successful card search by name"""
        from api_integrations import ScryfallAPI
        
        api = ScryfallAPI()
        
        with patch('api_integrations.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'id': 'abc123',
                'name': 'Lightning Bolt',
                'set': 'm21',
                'set_name': 'Core Set 2021',
                'collector_number': '199',
                'rarity': 'rare',
                'type_line': 'Instant',
                'colors': ['R'],
                'mana_cost': '{R}',
                'image_uris': {'normal': 'https://example.com/image.jpg'},
                'oracle_text': 'Deal 3 damage',
                'flavor_text': 'Flavor',
                'artist': 'Artist Name',
                'lang': 'en',
                'prices': {'usd': '1.50', 'usd_foil': '3.00'}
            }
            mock_get.return_value = mock_response
            
            result = api.search_card_by_name('Lightning Bolt')
        
        assert result is not None
        assert result['name'] == 'Lightning Bolt'
        assert result['tcg'] == 'mtg'
        
    def test_search_card_by_name_not_found(self):
        """Test card search when card not found"""
        from api_integrations import ScryfallAPI
        
        api = ScryfallAPI()
        
        with patch('api_integrations.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response
            
            result = api.search_card_by_name('NonexistentCard12345')
        
        assert result is None
        
    def test_search_card_by_name_api_error(self):
        """Test card search with API error"""
        from api_integrations import ScryfallAPI
        
        api = ScryfallAPI()
        
        with patch('api_integrations.requests.get') as mock_get:
            mock_get.side_effect = requests.RequestException("Network error")
            
            result = api.search_card_by_name('Lightning Bolt')
        
        assert result is None
        
    def test_get_card_by_set_and_number(self):
        """Test getting card by set code and collector number"""
        from api_integrations import ScryfallAPI
        
        api = ScryfallAPI()
        
        with patch('api_integrations.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'id': 'abc123',
                'name': 'Lightning Bolt',
                'set': 'm21',
                'set_name': 'Core Set 2021',
                'collector_number': '199',
                'rarity': 'rare',
                'type_line': 'Instant',
                'colors': ['R'],
                'image_uris': {'normal': 'https://example.com/image.jpg'},
                'prices': {}
            }
            mock_get.return_value = mock_response
            
            result = api.get_card_by_set_and_number('m21', '199')
        
        assert result is not None
        assert result['set_code'] == 'm21'
        
    def test_search_cards(self):
        """Test searching multiple cards"""
        from api_integrations import ScryfallAPI
        
        api = ScryfallAPI()
        
        with patch('api_integrations.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'data': [
                    {
                        'id': 'card1',
                        'name': 'Card 1',
                        'set': 'm21',
                        'colors': [],
                        'image_uris': {'normal': 'url1'},
                        'prices': {}
                    },
                    {
                        'id': 'card2',
                        'name': 'Card 2',
                        'set': 'm21',
                        'colors': [],
                        'image_uris': {'normal': 'url2'},
                        'prices': {}
                    }
                ]
            }
            mock_get.return_value = mock_response
            
            results = api.search_cards('set:m21')
        
        assert len(results) == 2
        
    def test_parse_double_faced_card(self):
        """Test parsing double-faced card data"""
        from api_integrations import ScryfallAPI
        
        api = ScryfallAPI()
        
        # Double-faced card has card_faces instead of image_uris at top level
        data = {
            'id': 'dfc-card',
            'name': 'Delver of Secrets // Insectile Aberration',
            'set': 'isd',
            'set_name': 'Innistrad',
            'collector_number': '51',
            'rarity': 'common',
            'type_line': 'Creature — Human Wizard // Creature — Human Insect',
            'mana_cost': '{U}',
            'card_faces': [
                {
                    'name': 'Delver of Secrets',
                    'colors': ['U'],
                    'image_uris': {'normal': 'https://example.com/front.jpg'}
                },
                {
                    'name': 'Insectile Aberration',
                    'colors': ['U'],
                    'image_uris': {'normal': 'https://example.com/back.jpg'}
                }
            ],
            'prices': {}
        }
        
        result = api._parse_card_data(data)
        
        assert result['image_url'] == 'https://example.com/front.jpg'
        assert 'U' in result['colors']








class TestCardAPIManager:
    """Tests for the unified API manager"""
    
    def test_search_card_mtg(self):
        """Test searching MTG card through manager"""
        from api_integrations import CardAPIManager
        
        manager = CardAPIManager()
        
        with patch.object(manager.scryfall, 'search_card_by_name') as mock_search:
            mock_search.return_value = {'name': 'Lightning Bolt', 'tcg': 'mtg'}
            
            result = manager.search_card('Lightning Bolt')
        
        mock_search.assert_called_once_with('Lightning Bolt')
        assert result['name'] == 'Lightning Bolt'
        

        

        
    def test_search_card_not_found(self):
        """Test searching card that doesn't exist"""
        from api_integrations import CardAPIManager
        
        manager = CardAPIManager()
        
        with patch.object(manager.scryfall, 'search_card_by_name') as mock_search:
            mock_search.return_value = None
            
            result = manager.search_card('NonexistentCard12345')
        
        assert result is None
        
    def test_get_card_price(self):
        """Test extracting price from card data"""
        from api_integrations import CardAPIManager
        
        manager = CardAPIManager()
        
        card_data = {'price_usd': '5.99'}
        price = manager.get_card_price(card_data)
        
        assert price == 5.99
        
    def test_get_card_price_no_price(self):
        """Test extracting price when not available"""
        from api_integrations import CardAPIManager
        
        manager = CardAPIManager()
        
        card_data = {}
        price = manager.get_card_price(card_data)
        
        assert price is None
        
    def test_get_card_price_invalid_format(self):
        """Test extracting price with invalid format"""
        from api_integrations import CardAPIManager
        
        manager = CardAPIManager()
        
        card_data = {'price_usd': 'not a number'}
        price = manager.get_card_price(card_data)
        
        assert price is None


class TestAPIErrorHandling:
    """Tests for API error handling"""
    
    def test_scryfall_timeout(self):
        """Test Scryfall API timeout handling"""
        from api_integrations import ScryfallAPI
        
        api = ScryfallAPI()
        
        with patch('api_integrations.requests.get') as mock_get:
            mock_get.side_effect = requests.Timeout("Connection timed out")
            
            result = api.search_card_by_name('Test Card')
        
        assert result is None
        

        



class TestDataParsing:
    """Tests for data parsing edge cases"""
    
    def test_scryfall_missing_fields(self):
        """Test Scryfall parsing with missing optional fields"""
        from api_integrations import ScryfallAPI
        
        api = ScryfallAPI()
        
        # Minimal card data
        data = {
            'id': 'minimal',
            'name': 'Minimal Card',
            'set': 'tst',
            'prices': {}
        }
        
        result = api._parse_card_data(data)
        
        assert result['name'] == 'Minimal Card'
        assert result['colors'] == ''
        

        

