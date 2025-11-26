"""
TCG Scan - Database Models
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import config
from logger import get_logger

# Initialize logger for this module
logger = get_logger('database')

Base = declarative_base()

class Card(Base):
    """Master card database - all known cards"""
    __tablename__ = 'cards'
    
    id = Column(Integer, primary_key=True)
    tcg = Column(String(20), nullable=False)  # mtg, pokemon, yugioh
    card_id = Column(String(100), unique=True, nullable=False)  # API card ID
    name = Column(String(200), nullable=False, index=True)
    set_code = Column(String(50), index=True)
    set_name = Column(String(200))
    collector_number = Column(String(20))
    rarity = Column(String(50), index=True)
    card_type = Column(String(100), index=True)
    colors = Column(String(50))  # Comma-separated
    mana_cost = Column(String(50))
    image_url = Column(String(500))
    image_hash = Column(String(64))  # Perceptual hash for recognition
    oracle_text = Column(Text)
    flavor_text = Column(Text)
    artist = Column(String(200))
    is_foil = Column(Boolean, default=False)
    language = Column(String(10), default='en')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    scanned_instances = relationship('ScannedCard', back_populates='card')
    price_history = relationship('PriceHistory', back_populates='card')
    
    def to_dict(self):
        # Get latest price from price_history
        price_eur = None
        price_usd = None
        if self.price_history:
            sorted_prices = sorted(self.price_history, key=lambda p: p.recorded_at, reverse=True)
            for ph in sorted_prices:
                if ph.currency == 'EUR' and price_eur is None:
                    price_eur = ph.price
                elif ph.currency == 'USD' and price_usd is None:
                    price_usd = ph.price
                if price_eur is not None and price_usd is not None:
                    break
        
        return {
            'id': self.id,
            'tcg': self.tcg,
            'card_id': self.card_id,
            'name': self.name,
            'set_code': self.set_code,
            'set_name': self.set_name,
            'collector_number': self.collector_number,
            'rarity': self.rarity,
            'card_type': self.card_type,
            'colors': self.colors.split(',') if self.colors else [],
            'mana_cost': self.mana_cost,
            'image_url': self.image_url,
            'is_foil': self.is_foil,
            'language': self.language,
            'price_eur': price_eur,
            'price_usd': price_usd
        }

class ScannedCard(Base):
    """Individual scanned card instances in user's collection"""
    __tablename__ = 'scanned_cards'
    
    id = Column(Integer, primary_key=True)
    card_id = Column(Integer, ForeignKey('cards.id'), nullable=False)
    collection_id = Column(Integer, ForeignKey('collections.id'))
    scan_date = Column(DateTime, default=datetime.utcnow)
    confidence_score = Column(Float)  # Recognition confidence
    condition = Column(String(20), default='NM')  # NM, LP, MP, HP, DMG
    is_foil = Column(Boolean, default=False)
    quantity = Column(Integer, default=1)
    bin_assignment = Column(Integer)  # Assigned bin number
    sorting_criteria = Column(String(50))  # Which criteria was used for sorting
    notes = Column(Text)
    image_path = Column(String(500))  # Path to scanned image
    
    # Relationships
    card = relationship('Card', back_populates='scanned_instances')
    collection = relationship('Collection', back_populates='cards')
    
    def to_dict(self, include_price=True):
        card_data = self.card.to_dict() if self.card else {}
        
        # Get latest price from price_history
        price_eur = None
        price_usd = None
        if include_price and self.card and self.card.price_history:
            # Sort by recorded_at descending and get latest
            sorted_prices = sorted(self.card.price_history, key=lambda p: p.recorded_at, reverse=True)
            for ph in sorted_prices:
                if ph.currency == 'EUR' and price_eur is None:
                    price_eur = ph.price
                elif ph.currency == 'USD' and price_usd is None:
                    price_usd = ph.price
                if price_eur is not None and price_usd is not None:
                    break
        
        scanned_data = {
            'id': self.id,
            'scan_date': self.scan_date.isoformat(),
            'confidence_score': self.confidence_score,
            'condition': self.condition,
            'is_foil': self.is_foil,
            'quantity': self.quantity,
            'bin_assignment': self.bin_assignment,
            'sorting_criteria': self.sorting_criteria,
            'notes': self.notes,
            'price_eur': price_eur,
            'price_usd': price_usd,
        }
        # Merge with scanned_data taking precedence
        return {**card_data, **scanned_data}

class Collection(Base):
    """User collections/folders"""
    __tablename__ = 'collections'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    tcg = Column(String(20))  # Filter by TCG
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    cards = relationship('ScannedCard', back_populates='collection')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'tcg': self.tcg,
            'card_count': len(self.cards),
            'created_at': self.created_at.isoformat()
        }

class PriceHistory(Base):
    """Price tracking history"""
    __tablename__ = 'price_history'
    
    id = Column(Integer, primary_key=True)
    card_id = Column(Integer, ForeignKey('cards.id'), nullable=False)
    price = Column(Float, nullable=False)
    price_source = Column(String(50))  # tcgplayer, cardmarket, etc.
    currency = Column(String(3), default='USD')
    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    card = relationship('Card', back_populates='price_history')
    
    def to_dict(self):
        return {
            'id': self.id,
            'card_id': self.card_id,
            'price': self.price,
            'price_source': self.price_source,
            'currency': self.currency,
            'recorded_at': self.recorded_at.isoformat()
        }

class SortingConfig(Base):
    """Saved sorting configurations"""
    __tablename__ = 'sorting_configs'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    tcg = Column(String(20))
    criteria = Column(String(50), nullable=False)  # alphabetic, set, color, type, rarity, price
    sub_criteria = Column(String(50))  # e.g., '1st_letter' for alphabetic
    bin_count = Column(Integer, default=6)
    bin_mapping = Column(JSON)  # Maps bins to values
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'tcg': self.tcg,
            'criteria': self.criteria,
            'sub_criteria': self.sub_criteria,
            'bin_count': self.bin_count,
            'bin_mapping': self.bin_mapping,
            'is_default': self.is_default
        }

# Database initialization
engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    """Initialize database tables"""
    logger.info("Initializing database...")
    try:
        Base.metadata.create_all(engine)
        logger.info(f"Database initialized successfully at {config.DATABASE_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise

def get_db():
    """Get database session"""
    logger.debug("Creating new database session")
    db = SessionLocal()
    try:
        return db
    except Exception as e:
        logger.error(f"Failed to create database session: {e}", exc_info=True)
        raise

if __name__ == '__main__':
    init_db()
