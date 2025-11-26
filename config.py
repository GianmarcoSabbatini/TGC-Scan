"""
TCG Scan - Configuration
"""
import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent

# Database
DATABASE_PATH = BASE_DIR / 'TCG Scan.db'
SQLALCHEMY_DATABASE_URI = f'sqlite:///{DATABASE_PATH}'

# Upload settings
UPLOAD_FOLDER = BASE_DIR / 'uploads'
UPLOAD_FOLDER.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

# Card recognition settings
RECOGNITION_CONFIDENCE_THRESHOLD = 0.75
IMAGE_HASH_THRESHOLD = 10  # Hamming distance for perceptual hash matching

# Supported TCG - Magic: The Gathering only
SUPPORTED_TCGS = {
    'mtg': {
        'name': 'Magic: The Gathering',
        'api': 'scryfall',
        'colors': ['W', 'U', 'B', 'R', 'G', 'C'],  # White, Blue, Black, Red, Green, Colorless
        'rarities': ['common', 'uncommon', 'rare', 'mythic'],
        'types': ['Creature', 'Instant', 'Sorcery', 'Enchantment', 'Artifact', 'Planeswalker', 'Land']
    }
}

# API Configuration - Scryfall only
SCRYFALL_API_BASE = 'https://api.scryfall.com'
SCRYFALL_RATE_LIMIT = 10  # requests per second

# Price tracking
PRICE_UPDATE_INTERVAL = 3600  # 1 hour in seconds
PRICE_TIERS = [
    {'name': 'Bulk', 'min': 0, 'max': 0.50},
    {'name': 'Low', 'min': 0.50, 'max': 2.00},
    {'name': 'Medium', 'min': 2.00, 'max': 10.00},
    {'name': 'High', 'min': 10.00, 'max': 50.00},
    {'name': 'Premium', 'min': 50.00, 'max': float('inf')}
]

# Sorting configuration
SORTING_CRITERIA = {
    'alphabetic': {
        'name': 'Alphabetic',
        'options': ['1st_letter', '2nd_letter', '3rd_letter']
    },
    'set': {
        'name': 'Set/Expansion',
        'options': []  # Populated dynamically
    },
    'color': {
        'name': 'Color',
        'options': []  # Populated based on TCG
    },
    'type': {
        'name': 'Card Type',
        'options': []  # Populated based on TCG
    },
    'rarity': {
        'name': 'Rarity',
        'options': []  # Populated based on TCG
    },
    'price': {
        'name': 'Price Tier',
        'options': [tier['name'] for tier in PRICE_TIERS]
    }
}

# Bin configuration
MAX_BINS = 20
DEFAULT_BIN_COUNT = 6

# Flask settings
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# WebSocket settings
SOCKETIO_ASYNC_MODE = 'threading'
