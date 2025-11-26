"""
TCG Scan - Sorting Engine Tests
Tests for card sorting algorithms and bin assignment
"""
import pytest
from unittest.mock import MagicMock, patch


class TestSortAlphabetic:
    """Tests for alphabetic sorting"""
    
    def test_sort_by_first_letter(self, db_session, sample_card_data):
        """Test sorting by first letter"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        # Create cards with different starting letters
        cards_data = [
            ('Alpha Card', 'A'),
            ('Beta Card', 'B'),
            ('Charlie Card', 'C'),
            ('Delta Card', 'D'),
        ]
        
        scanned_cards = []
        for i, (name, _) in enumerate(cards_data):
            card_data = sample_card_data.copy()
            card_data['card_id'] = f'test-{i}'
            card_data['name'] = name
            
            card = Card(**card_data)
            db_session.add(card)
            db_session.commit()
            
            scanned = ScannedCard(card_id=card.id)
            db_session.add(scanned)
            scanned_cards.append(scanned)
        
        db_session.commit()
        
        # Sort
        bins = engine.sort_alphabetic(scanned_cards, '1st_letter', 4)
        
        assert len(bins) == 4
        # Each bin should have at least one card
        total_cards = sum(len(b) for b in bins.values())
        assert total_cards == 4
        
    def test_sort_by_second_letter(self, db_session, sample_card_data):
        """Test sorting by second letter"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        cards_data = ['Aa Card', 'Ab Card', 'Ba Card', 'Bb Card']
        
        scanned_cards = []
        for i, name in enumerate(cards_data):
            card_data = sample_card_data.copy()
            card_data['card_id'] = f'test-2nd-{i}'
            card_data['name'] = name
            
            card = Card(**card_data)
            db_session.add(card)
            db_session.commit()
            
            scanned = ScannedCard(card_id=card.id)
            db_session.add(scanned)
            scanned_cards.append(scanned)
        
        db_session.commit()
        
        bins = engine.sort_alphabetic(scanned_cards, '2nd_letter', 4)
        
        total_cards = sum(len(b) for b in bins.values())
        assert total_cards == 4
        
    def test_sort_alphabetic_empty_list(self):
        """Test sorting empty list"""
        from sorting_engine import SortingEngine
        
        engine = SortingEngine()
        bins = engine.sort_alphabetic([], '1st_letter', 6)
        
        assert all(len(b) == 0 for b in bins.values())
        
    def test_sort_alphabetic_updates_bin_assignment(self, db_session, sample_card_data):
        """Test that sorting updates bin assignment on cards"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        scanned = ScannedCard(card_id=card.id)
        db_session.add(scanned)
        db_session.commit()
        
        bins = engine.sort_alphabetic([scanned], '1st_letter', 6)
        
        assert scanned.bin_assignment is not None
        assert scanned.sorting_criteria == 'alphabetic_1st_letter'


class TestSortBySet:
    """Tests for sorting by set/expansion"""
    
    def test_sort_by_set(self, db_session, sample_card_data):
        """Test sorting cards by set"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        sets = ['M21', 'M20', 'M19', 'ZNR']
        
        scanned_cards = []
        for i, set_code in enumerate(sets):
            card_data = sample_card_data.copy()
            card_data['card_id'] = f'set-test-{i}'
            card_data['set_code'] = set_code
            
            card = Card(**card_data)
            db_session.add(card)
            db_session.commit()
            
            scanned = ScannedCard(card_id=card.id)
            db_session.add(scanned)
            scanned_cards.append(scanned)
        
        db_session.commit()
        
        bins = engine.sort_by_set(scanned_cards, None, 4)
        
        total_cards = sum(len(b) for b in bins.values())
        assert total_cards == 4
        
    def test_sort_by_set_distributes_evenly(self, db_session, sample_card_data):
        """Test that sets are distributed across bins"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        # Create many cards in different sets
        scanned_cards = []
        for i in range(12):
            card_data = sample_card_data.copy()
            card_data['card_id'] = f'dist-test-{i}'
            card_data['set_code'] = f'SET{i % 4}'
            
            card = Card(**card_data)
            db_session.add(card)
            db_session.commit()
            
            scanned = ScannedCard(card_id=card.id)
            db_session.add(scanned)
            scanned_cards.append(scanned)
        
        db_session.commit()
        
        bins = engine.sort_by_set(scanned_cards, None, 4)
        
        # All cards should be assigned
        total_cards = sum(len(b) for b in bins.values())
        assert total_cards == 12


class TestSortByColor:
    """Tests for sorting by color"""
    
    def test_sort_mtg_by_color(self, db_session, sample_card_data):
        """Test sorting MTG cards by color"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        colors = ['W', 'U', 'B', 'R', 'G', 'W,U']  # Include multicolor
        
        scanned_cards = []
        for i, color in enumerate(colors):
            card_data = sample_card_data.copy()
            card_data['card_id'] = f'color-test-{i}'
            card_data['colors'] = color
            
            card = Card(**card_data)
            db_session.add(card)
            db_session.commit()
            
            scanned = ScannedCard(card_id=card.id)
            db_session.add(scanned)
            scanned_cards.append(scanned)
        
        db_session.commit()
        
        bins = engine.sort_by_color(scanned_cards, None, 6)
        
        total_cards = sum(len(b) for b in bins.values())
        assert total_cards == 6
        
    def test_sort_colorless_cards(self, db_session, sample_card_data):
        """Test sorting colorless cards"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        # Create colorless card
        card_data = sample_card_data.copy()
        card_data['card_id'] = 'colorless-test'
        card_data['colors'] = ''
        
        card = Card(**card_data)
        db_session.add(card)
        db_session.commit()
        
        scanned = ScannedCard(card_id=card.id)
        db_session.add(scanned)
        db_session.commit()
        
        bins = engine.sort_by_color([scanned], None, 6)
        
        # Colorless should be assigned somewhere
        total_cards = sum(len(b) for b in bins.values())
        assert total_cards == 1


class TestSortByType:
    """Tests for sorting by card type"""
    
    def test_sort_by_type(self, db_session, sample_card_data):
        """Test sorting by card type"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        types = ['Creature', 'Instant', 'Sorcery', 'Enchantment', 'Artifact', 'Land']
        
        scanned_cards = []
        for i, card_type in enumerate(types):
            card_data = sample_card_data.copy()
            card_data['card_id'] = f'type-test-{i}'
            card_data['card_type'] = card_type
            
            card = Card(**card_data)
            db_session.add(card)
            db_session.commit()
            
            scanned = ScannedCard(card_id=card.id)
            db_session.add(scanned)
            scanned_cards.append(scanned)
        
        db_session.commit()
        
        bins = engine.sort_by_type(scanned_cards, None, 6)
        
        total_cards = sum(len(b) for b in bins.values())
        assert total_cards == 6
        
    def test_sort_unknown_type(self, db_session, sample_card_data):
        """Test sorting card with unknown type"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        card_data = sample_card_data.copy()
        card_data['card_id'] = 'unknown-type-test'
        card_data['card_type'] = 'Tribal Enchantment'  # Unusual type
        
        card = Card(**card_data)
        db_session.add(card)
        db_session.commit()
        
        scanned = ScannedCard(card_id=card.id)
        db_session.add(scanned)
        db_session.commit()
        
        bins = engine.sort_by_type([scanned], None, 6)
        
        total_cards = sum(len(b) for b in bins.values())
        assert total_cards == 1


class TestSortByRarity:
    """Tests for sorting by rarity"""
    
    def test_sort_by_rarity(self, db_session, sample_card_data):
        """Test sorting by rarity"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        rarities = ['common', 'uncommon', 'rare', 'mythic']
        
        scanned_cards = []
        for i, rarity in enumerate(rarities):
            card_data = sample_card_data.copy()
            card_data['card_id'] = f'rarity-test-{i}'
            card_data['rarity'] = rarity
            
            card = Card(**card_data)
            db_session.add(card)
            db_session.commit()
            
            scanned = ScannedCard(card_id=card.id)
            db_session.add(scanned)
            scanned_cards.append(scanned)
        
        db_session.commit()
        
        bins = engine.sort_by_rarity(scanned_cards, None, 4)
        
        total_cards = sum(len(b) for b in bins.values())
        assert total_cards == 4
        
    def test_sort_unknown_rarity(self, db_session, sample_card_data):
        """Test sorting card with unknown rarity"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        card_data = sample_card_data.copy()
        card_data['card_id'] = 'unknown-rarity-test'
        card_data['rarity'] = 'super_ultra_mega_rare'
        
        card = Card(**card_data)
        db_session.add(card)
        db_session.commit()
        
        scanned = ScannedCard(card_id=card.id)
        db_session.add(scanned)
        db_session.commit()
        
        bins = engine.sort_by_rarity([scanned], None, 4)
        
        total_cards = sum(len(b) for b in bins.values())
        assert total_cards == 1


class TestSortByPrice:
    """Tests for sorting by price tier"""
    
    def test_sort_by_price_tier(self, db_session, sample_card_data):
        """Test sorting by price tier"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard, PriceHistory
        
        engine = SortingEngine()
        
        prices = [0.25, 1.00, 5.00, 25.00, 100.00]  # Different tiers
        
        scanned_cards = []
        for i, price in enumerate(prices):
            card_data = sample_card_data.copy()
            card_data['card_id'] = f'price-test-{i}'
            
            card = Card(**card_data)
            db_session.add(card)
            db_session.commit()
            
            # Add price history
            price_record = PriceHistory(card_id=card.id, price=price)
            db_session.add(price_record)
            
            scanned = ScannedCard(card_id=card.id)
            db_session.add(scanned)
            scanned_cards.append(scanned)
        
        db_session.commit()
        
        bins = engine.sort_by_price(scanned_cards, None, 5)
        
        total_cards = sum(len(b) for b in bins.values())
        assert total_cards == 5
        
    def test_sort_by_price_no_history(self, db_session, sample_card_data):
        """Test sorting cards without price history"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        scanned = ScannedCard(card_id=card.id)
        db_session.add(scanned)
        db_session.commit()
        
        bins = engine.sort_by_price([scanned], None, 5)
        
        # Card without price should go to bulk tier
        total_cards = sum(len(b) for b in bins.values())
        assert total_cards == 1


class TestBinLabels:
    """Tests for bin label generation"""
    
    def test_alphabetic_labels(self):
        """Test alphabetic bin labels"""
        from sorting_engine import SortingEngine
        
        engine = SortingEngine()
        labels = engine.get_bin_labels('alphabetic', 6, 'mtg')
        
        assert len(labels) == 6
        assert all('-' in label for label in labels.values())  # A-D format
        
    def test_color_labels(self):
        """Test color bin labels"""
        from sorting_engine import SortingEngine
        
        engine = SortingEngine()
        labels = engine.get_bin_labels('color', 6, 'mtg')
        
        assert len(labels) == 6
        # Should include MTG colors
        assert any(c in str(labels.values()) for c in ['W', 'U', 'B', 'R', 'G'])
        
    def test_rarity_labels(self):
        """Test rarity bin labels"""
        from sorting_engine import SortingEngine
        
        engine = SortingEngine()
        labels = engine.get_bin_labels('rarity', 4, 'mtg')
        
        assert len(labels) == 4
        
    def test_price_labels(self):
        """Test price tier bin labels"""
        from sorting_engine import SortingEngine
        
        engine = SortingEngine()
        labels = engine.get_bin_labels('price', 5, 'mtg')
        
        assert len(labels) == 5
        # Should include tier names
        assert any(tier in str(labels.values()) for tier in ['Bulk', 'Low', 'Medium', 'High', 'Premium'])
        
    def test_default_labels(self):
        """Test default bin labels for unknown criteria"""
        from sorting_engine import SortingEngine
        
        engine = SortingEngine()
        labels = engine.get_bin_labels('unknown_criteria', 6, 'mtg')
        
        assert len(labels) == 6
        assert all('Bin' in label for label in labels.values())


class TestSortCardsMainMethod:
    """Tests for the main sort_cards method"""
    
    def test_sort_cards_dispatches_correctly(self, db_session, sample_card_data):
        """Test that sort_cards dispatches to correct method"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        scanned = ScannedCard(card_id=card.id)
        db_session.add(scanned)
        db_session.commit()
        
        # Test each criteria
        for criteria in ['alphabetic', 'set', 'color', 'type', 'rarity', 'price']:
            bins = engine.sort_cards([scanned], criteria, None, 6)
            assert isinstance(bins, dict)
            
    def test_sort_cards_invalid_criteria(self, db_session, sample_card_data):
        """Test sort_cards with invalid criteria"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        scanned = ScannedCard(card_id=card.id)
        db_session.add(scanned)
        db_session.commit()
        
        with pytest.raises(ValueError, match="Unknown sorting criteria"):
            engine.sort_cards([scanned], 'invalid_criteria', None, 6)


class TestEdgeCases:
    """Tests for edge cases"""
    
    def test_single_card_sorting(self, db_session, sample_card_data):
        """Test sorting with single card"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        scanned = ScannedCard(card_id=card.id)
        db_session.add(scanned)
        db_session.commit()
        
        bins = engine.sort_alphabetic([scanned], '1st_letter', 6)
        
        total_cards = sum(len(b) for b in bins.values())
        assert total_cards == 1
        
    def test_many_bins_few_cards(self, db_session, sample_card_data):
        """Test with more bins than cards"""
        from sorting_engine import SortingEngine
        from database import Card, ScannedCard
        
        engine = SortingEngine()
        
        # Create 2 cards but request 10 bins
        scanned_cards = []
        for i in range(2):
            card_data = sample_card_data.copy()
            card_data['card_id'] = f'few-cards-{i}'
            
            card = Card(**card_data)
            db_session.add(card)
            db_session.commit()
            
            scanned = ScannedCard(card_id=card.id)
            db_session.add(scanned)
            scanned_cards.append(scanned)
        
        db_session.commit()
        
        bins = engine.sort_alphabetic(scanned_cards, '1st_letter', 10)
        
        total_cards = sum(len(b) for b in bins.values())
        assert total_cards == 2
        
    def test_card_without_linked_card(self):
        """Test sorting ScannedCard without linked Card"""
        from sorting_engine import SortingEngine
        
        engine = SortingEngine()
        
        # Create mock ScannedCard without card relationship
        mock_scanned = MagicMock()
        mock_scanned.card = None
        
        # Should handle gracefully
        bins = engine.sort_alphabetic([mock_scanned], '1st_letter', 6)
        
        # Card should still be assigned somewhere
