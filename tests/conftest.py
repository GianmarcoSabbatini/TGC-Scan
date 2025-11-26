"""
TCG Scan - Test Configuration
Shared fixtures and configuration for all tests
"""
import pytest
import os
import sys
import tempfile
import uuid
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Test database configuration
TEST_DATABASE_URI = 'sqlite:///:memory:'


@pytest.fixture(scope='function')
def test_engine():
    """Create test database engine - new engine per test"""
    from database import Base
    engine = create_engine(TEST_DATABASE_URI)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope='function')
def db_session(test_engine):
    """Create a new database session for each test"""
    from database import Base
    
    Session = sessionmaker(bind=test_engine)
    session = Session()
    
    yield session
    
    # Cleanup
    session.rollback()
    session.close()


@pytest.fixture(scope='function')
def app():
    """Create test Flask application"""
    from app import app as flask_app
    
    flask_app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': TEST_DATABASE_URI,
    })
    
    yield flask_app


@pytest.fixture(scope='function')
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture(scope='function')
def temp_upload_dir():
    """Create temporary upload directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_card_data():
    """Sample card data for testing - unique per call"""
    unique_id = str(uuid.uuid4())[:8]
    return {
        'tcg': 'mtg',
        'card_id': f'test-card-{unique_id}',
        'name': 'Lightning Bolt',
        'set_code': 'M21',
        'set_name': 'Core Set 2021',
        'collector_number': '199',
        'rarity': 'rare',
        'card_type': 'Instant',
        'colors': 'R',
        'mana_cost': '{R}',
        'image_url': 'https://example.com/card.jpg',
        'image_hash': 'abcd1234' * 8,
        'oracle_text': 'Lightning Bolt deals 3 damage to any target.',
        'artist': 'Christopher Moeller',
        'language': 'en'
    }


@pytest.fixture
def sample_pokemon_card_data():
    """Sample Pokemon card data for testing - unique per call"""
    unique_id = str(uuid.uuid4())[:8]
    return {
        'tcg': 'pokemon',
        'card_id': f'swsh1-{unique_id}',
        'name': 'Pikachu VMAX',
        'set_code': 'SWSH01',
        'set_name': 'Sword & Shield',
        'collector_number': '25',
        'rarity': 'Rare Holo',
        'card_type': 'Lightning',
        'colors': 'Lightning',
        'image_url': 'https://example.com/pikachu.jpg',
        'image_hash': 'efgh5678' * 8,
    }


@pytest.fixture
def sample_yugioh_card_data():
    """Sample Yu-Gi-Oh! card data for testing - unique per call"""
    unique_id = str(uuid.uuid4())[:8]
    return {
        'tcg': 'yugioh',
        'card_id': f'ygo-{unique_id}',
        'name': 'Dark Magician',
        'set_code': 'LOB',
        'set_name': 'Legend of Blue Eyes White Dragon',
        'rarity': 'Ultra Rare',
        'card_type': 'Monster',
        'colors': 'DARK',
        'oracle_text': 'The ultimate wizard in terms of attack and defense.',
    }


@pytest.fixture
def sample_scanned_card(db_session, sample_card_data):
    """Create a sample scanned card in the database"""
    from database import Card, ScannedCard
    
    # Create card
    card = Card(**sample_card_data)
    db_session.add(card)
    db_session.commit()
    
    # Create scanned instance
    scanned = ScannedCard(
        card_id=card.id,
        confidence_score=0.95,
        condition='NM',
        is_foil=False,
        quantity=1
    )
    db_session.add(scanned)
    db_session.commit()
    
    return scanned


@pytest.fixture
def sample_collection(db_session):
    """Create a sample collection"""
    from database import Collection
    
    collection = Collection(
        name='Test Collection',
        description='A test collection for unit tests',
        tcg='mtg'
    )
    db_session.add(collection)
    db_session.commit()
    
    return collection


@pytest.fixture
def mock_image_file(temp_upload_dir):
    """Create a mock image file for testing"""
    import numpy as np
    from PIL import Image
    
    # Create a simple test image
    img_array = np.random.randint(0, 255, (300, 200, 3), dtype=np.uint8)
    img = Image.fromarray(img_array)
    
    filepath = temp_upload_dir / 'test_card.jpg'
    img.save(filepath)
    
    return filepath
