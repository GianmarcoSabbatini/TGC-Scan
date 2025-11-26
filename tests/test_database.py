"""
TCG Scan - Database Tests
Tests for database models, relationships, and operations
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError


class TestCardModel:
    """Tests for the Card model"""
    
    def test_create_card(self, db_session, sample_card_data):
        """Test creating a new card"""
        from database import Card
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        assert card.id is not None
        assert card.name == 'Lightning Bolt'
        assert card.tcg == 'mtg'
        
    def test_card_unique_constraint(self, db_session, sample_card_data):
        """Test that card_id must be unique"""
        from database import Card
        
        card1 = Card(**sample_card_data)
        db_session.add(card1)
        db_session.commit()
        
        # Try to create duplicate
        card2 = Card(**sample_card_data)
        db_session.add(card2)
        
        with pytest.raises(IntegrityError):
            db_session.commit()
            
    def test_card_to_dict(self, db_session, sample_card_data):
        """Test card serialization to dictionary"""
        from database import Card
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        card_dict = card.to_dict()
        
        assert card_dict['name'] == 'Lightning Bolt'
        assert card_dict['tcg'] == 'mtg'
        assert card_dict['set_code'] == 'M21'
        assert isinstance(card_dict['colors'], list)
        
    def test_card_colors_parsing(self, db_session):
        """Test that colors are properly parsed"""
        from database import Card
        
        card = Card(
            tcg='mtg',
            card_id='test-multicolor',
            name='Test Card',
            colors='W,U,B'
        )
        db_session.add(card)
        db_session.commit()
        
        card_dict = card.to_dict()
        assert card_dict['colors'] == ['W', 'U', 'B']
        
    def test_card_empty_colors(self, db_session):
        """Test card with no colors (colorless)"""
        from database import Card
        
        card = Card(
            tcg='mtg',
            card_id='test-colorless',
            name='Mox Diamond',
            colors=''
        )
        db_session.add(card)
        db_session.commit()
        
        card_dict = card.to_dict()
        assert card_dict['colors'] == []
        
    def test_card_timestamps(self, db_session, sample_card_data):
        """Test that timestamps are set correctly"""
        from database import Card
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        assert card.created_at is not None
        assert card.updated_at is not None
        assert isinstance(card.created_at, datetime)


class TestScannedCardModel:
    """Tests for the ScannedCard model"""
    
    def test_create_scanned_card(self, db_session, sample_card_data):
        """Test creating a scanned card instance"""
        from database import Card, ScannedCard
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        scanned = ScannedCard(
            card_id=card.id,
            confidence_score=0.95,
            condition='NM',
            quantity=1
        )
        db_session.add(scanned)
        db_session.commit()
        
        assert scanned.id is not None
        assert scanned.card_id == card.id
        assert scanned.confidence_score == 0.95
        
    def test_scanned_card_relationship(self, db_session, sample_card_data):
        """Test relationship between ScannedCard and Card"""
        from database import Card, ScannedCard
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        scanned = ScannedCard(card_id=card.id, confidence_score=0.9)
        db_session.add(scanned)
        db_session.commit()
        
        # Test relationship
        assert scanned.card is not None
        assert scanned.card.name == 'Lightning Bolt'
        
        # Test reverse relationship
        assert len(card.scanned_instances) == 1
        
    def test_scanned_card_to_dict(self, db_session, sample_card_data):
        """Test scanned card serialization includes card data"""
        from database import Card, ScannedCard
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        scanned = ScannedCard(
            card_id=card.id,
            confidence_score=0.95,
            condition='LP',
            is_foil=True,
            quantity=2
        )
        db_session.add(scanned)
        db_session.commit()
        
        # Refresh to load the relationship
        db_session.refresh(scanned)
        
        scanned_dict = scanned.to_dict()
        
        assert scanned_dict['name'] == 'Lightning Bolt'
        assert scanned_dict['condition'] == 'LP'
        assert scanned_dict['is_foil'] is True
        assert scanned_dict['quantity'] == 2
        assert 'scan_date' in scanned_dict
        
    def test_scanned_card_default_values(self, db_session, sample_card_data):
        """Test default values for scanned card"""
        from database import Card, ScannedCard
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        scanned = ScannedCard(card_id=card.id)
        db_session.add(scanned)
        db_session.commit()
        
        assert scanned.condition == 'NM'
        assert scanned.is_foil is False
        assert scanned.quantity == 1


class TestCollectionModel:
    """Tests for the Collection model"""
    
    def test_create_collection(self, db_session):
        """Test creating a collection"""
        from database import Collection
        
        collection = Collection(
            name='My MTG Collection',
            description='All my Magic cards',
            tcg='mtg'
        )
        db_session.add(collection)
        db_session.commit()
        
        assert collection.id is not None
        assert collection.name == 'My MTG Collection'
        
    def test_collection_card_relationship(self, db_session, sample_card_data):
        """Test adding cards to collection"""
        from database import Card, ScannedCard, Collection
        
        # Create collection
        collection = Collection(name='Test Collection', tcg='mtg')
        db_session.add(collection)
        db_session.commit()
        
        # Create card
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        # Add scanned card to collection
        scanned = ScannedCard(
            card_id=card.id,
            collection_id=collection.id
        )
        db_session.add(scanned)
        db_session.commit()
        
        assert len(collection.cards) == 1
        assert collection.cards[0].card.name == 'Lightning Bolt'
        
    def test_collection_to_dict(self, db_session, sample_card_data):
        """Test collection serialization with card count"""
        from database import Card, ScannedCard, Collection
        
        collection = Collection(name='Test Collection', tcg='mtg')
        db_session.add(collection)
        db_session.commit()
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        scanned = ScannedCard(card_id=card.id, collection_id=collection.id)
        db_session.add(scanned)
        db_session.commit()
        
        collection_dict = collection.to_dict()
        
        assert collection_dict['name'] == 'Test Collection'
        assert collection_dict['card_count'] == 1


class TestPriceHistoryModel:
    """Tests for the PriceHistory model"""
    
    def test_create_price_history(self, db_session, sample_card_data):
        """Test creating price history entry"""
        from database import Card, PriceHistory
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        price = PriceHistory(
            card_id=card.id,
            price=5.99,
            price_source='tcgplayer',
            currency='USD'
        )
        db_session.add(price)
        db_session.commit()
        
        assert price.id is not None
        assert price.price == 5.99
        
    def test_price_history_relationship(self, db_session, sample_card_data):
        """Test price history relationship with card"""
        from database import Card, PriceHistory
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        # Add multiple price entries
        prices = [
            PriceHistory(card_id=card.id, price=5.00),
            PriceHistory(card_id=card.id, price=5.50),
            PriceHistory(card_id=card.id, price=6.00),
        ]
        db_session.add_all(prices)
        db_session.commit()
        
        assert len(card.price_history) == 3
        
    def test_price_history_to_dict(self, db_session, sample_card_data):
        """Test price history serialization"""
        from database import Card, PriceHistory
        
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        price = PriceHistory(
            card_id=card.id,
            price=10.50,
            price_source='scryfall',
            currency='EUR'
        )
        db_session.add(price)
        db_session.commit()
        
        price_dict = price.to_dict()
        
        assert price_dict['price'] == 10.50
        assert price_dict['price_source'] == 'scryfall'
        assert price_dict['currency'] == 'EUR'
        assert 'recorded_at' in price_dict


class TestSortingConfigModel:
    """Tests for the SortingConfig model"""
    
    def test_create_sorting_config(self, db_session):
        """Test creating a sorting configuration"""
        from database import SortingConfig
        
        config = SortingConfig(
            name='My Sorting',
            tcg='mtg',
            criteria='color',
            bin_count=6,
            bin_mapping={'1': 'White', '2': 'Blue', '3': 'Black'}
        )
        db_session.add(config)
        db_session.commit()
        
        assert config.id is not None
        assert config.criteria == 'color'
        assert config.bin_count == 6
        
    def test_sorting_config_to_dict(self, db_session):
        """Test sorting config serialization"""
        from database import SortingConfig
        
        config = SortingConfig(
            name='Test Config',
            criteria='rarity',
            bin_count=4,
            bin_mapping={'1': 'common', '2': 'uncommon', '3': 'rare', '4': 'mythic'}
        )
        db_session.add(config)
        db_session.commit()
        
        config_dict = config.to_dict()
        
        assert config_dict['name'] == 'Test Config'
        assert config_dict['criteria'] == 'rarity'
        assert config_dict['bin_mapping'] is not None


class TestDatabaseOperations:
    """Tests for database operations"""
    
    def test_init_db(self):
        """Test database initialization"""
        from database import init_db
        
        # Should not raise any errors
        init_db()
        
    def test_get_db(self):
        """Test getting database session"""
        from database import get_db
        
        db = get_db()
        assert db is not None
        db.close()
        
    def test_session_rollback_on_error(self, db_session, sample_card_data):
        """Test that session can be rolled back after error"""
        from database import Card
        
        card1 = Card(**sample_card_data)
        db_session.add(card1)
        db_session.commit()
        
        # Create duplicate (should fail)
        card2 = Card(**sample_card_data)
        db_session.add(card2)
        
        try:
            db_session.commit()
        except IntegrityError:
            db_session.rollback()
        
        # Session should still be usable
        sample_card_data['card_id'] = 'different-id'
        card3 = Card(**sample_card_data)
        db_session.add(card3)
        db_session.commit()
        
        assert card3.id is not None
