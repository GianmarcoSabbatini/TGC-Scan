"""
TCG Scan - Main Flask Application
REST API and WebSocket server for the TCG Scan system
"""
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import os
from werkzeug.utils import secure_filename
from datetime import datetime
import threading
import time

import config
from database import init_db, get_db, Card, ScannedCard, Collection, SortingConfig, PriceHistory
from card_recognition import CardRecognitionEngine, download_and_hash_card_image
from sorting_engine import SortingEngine
from price_tracker import PriceTracker
from api_integrations import CardAPIManager
from logger import get_logger, log_api_call, PerformanceLogger

# Initialize logger for this module
logger = get_logger('app')

# Initialize Flask app
logger.info("Initializing Flask application...")
app = Flask(__name__, static_folder='static', static_url_path='')
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=config.SOCKETIO_ASYNC_MODE)

# Initialize components
logger.info("Initializing application components...")
recognition_engine = CardRecognitionEngine()
sorting_engine = SortingEngine()
price_tracker = PriceTracker()
api_manager = CardAPIManager()

# Initialize database
init_db()
logger.info("Application initialization complete")

# ============================================================================
# BACKGROUND PRICE UPDATE TASK
# ============================================================================

class PriceUpdateScheduler:
    """Background scheduler for automatic price updates"""
    
    def __init__(self, interval_hours: int = 6):
        self.interval_seconds = interval_hours * 3600
        self.running = False
        self.thread = None
        self.last_update = None
        logger.info(f"PriceUpdateScheduler initialized | interval={interval_hours}h")
    
    def start(self):
        """Start the background price update thread"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("Price update scheduler started")
    
    def stop(self):
        """Stop the background thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Price update scheduler stopped")
    
    def _run(self):
        """Background thread main loop"""
        while self.running:
            try:
                logger.info("Starting scheduled price update...")
                stats = price_tracker.update_all_prices()
                self.last_update = datetime.now(datetime.UTC) if hasattr(datetime, 'UTC') else datetime.utcnow()
                
                # Notify connected clients
                socketio.emit('prices_updated', {
                    'timestamp': self.last_update.isoformat(),
                    'stats': stats
                })
                
                logger.info(f"Scheduled price update complete | stats={stats}")
                
            except Exception as e:
                logger.error(f"Scheduled price update error: {e}", exc_info=True)
            
            # Sleep in small intervals to allow clean shutdown
            for _ in range(self.interval_seconds):
                if not self.running:
                    break
                time.sleep(1)
    
    def get_status(self):
        """Get scheduler status"""
        return {
            'running': self.running,
            'interval_hours': self.interval_seconds / 3600,
            'last_update': self.last_update.isoformat() if self.last_update else None
        }


class HashDownloadWorker:
    """Background worker to download and compute image hashes for cards"""
    
    def __init__(self):
        self.running = False
        self.thread = None
        self.progress = {'total': 0, 'processed': 0, 'current_card': None}
        self.last_run = None
        logger.info("HashDownloadWorker initialized")
    
    def start(self, set_code: str = None):
        """Start downloading hashes in background"""
        if self.running:
            logger.warning("Hash download already running")
            return False
        
        self.running = True
        self.progress = {'total': 0, 'processed': 0, 'current_card': None, 'set_code': set_code}
        self.thread = threading.Thread(target=self._run, args=(set_code,), daemon=True)
        self.thread.start()
        logger.info(f"Hash download worker started | set_code={set_code}")
        return True
    
    def stop(self):
        """Stop the background thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Hash download worker stopped")
    
    def _run(self, set_code: str = None):
        """Background thread to download hashes"""
        db = get_db()
        try:
            # Get cards without hash
            query = db.query(Card).filter(Card.image_hash == None)
            if set_code:
                query = query.filter(Card.set_code == set_code.lower())
            
            cards = query.all()
            self.progress['total'] = len(cards)
            
            logger.info(f"Hash download: Processing {len(cards)} cards without hash")
            
            # Emit start event
            socketio.emit('hash_download_started', {
                'total': len(cards),
                'set_code': set_code
            })
            
            for idx, card in enumerate(cards):
                if not self.running:
                    logger.info("Hash download stopped by user")
                    break
                
                try:
                    # Download and hash image
                    card_data = {'image_url': card.image_url}
                    image_hash = download_and_hash_card_image(card_data)
                    
                    if image_hash:
                        card.image_hash = image_hash
                        db.commit()
                    
                    self.progress['processed'] = idx + 1
                    self.progress['current_card'] = card.name
                    
                    # Emit progress every 10 cards
                    if (idx + 1) % 10 == 0 or idx == len(cards) - 1:
                        socketio.emit('hash_download_progress', {
                            'processed': idx + 1,
                            'total': len(cards),
                            'percent': round((idx + 1) / len(cards) * 100, 1),
                            'current_card': card.name
                        })
                        logger.debug(f"Hash download progress: {idx + 1}/{len(cards)}")
                    
                    # Rate limit: ~100ms delay between downloads
                    time.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"Error hashing card {card.name}: {e}")
                    continue
            
            self.last_run = datetime.now()
            logger.info(f"Hash download complete | processed={self.progress['processed']}/{self.progress['total']}")
            
            # Emit completion
            socketio.emit('hash_download_complete', {
                'processed': self.progress['processed'],
                'total': self.progress['total']
            })
            
        except Exception as e:
            logger.error(f"Hash download error: {e}", exc_info=True)
            socketio.emit('hash_download_error', {'error': str(e)})
        finally:
            db.close()
            self.running = False
    
    def get_status(self):
        """Get worker status"""
        return {
            'running': self.running,
            'progress': self.progress,
            'last_run': self.last_run.isoformat() if self.last_run else None
        }


# Initialize workers
price_scheduler = PriceUpdateScheduler(interval_hours=6)
hash_worker = HashDownloadWorker()

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in config.ALLOWED_EXTENSIONS

# ============================================================================
# CARD SCANNING & RECOGNITION ENDPOINTS
# ============================================================================

@app.route('/api/scan/upload', methods=['POST'])
def upload_scan():
    """Upload and recognize a card image"""
    logger.info(f"Scan upload request received")
    
    if 'file' not in request.files:
        logger.warning("Scan upload: No file provided")
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        logger.warning("Scan upload: Empty filename")
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        logger.warning(f"Scan upload: Invalid file type | filename={file.filename}")
        return jsonify({'error': 'Invalid file type'}), 400
    
    try:
        # Save uploaded file
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(config.UPLOAD_FOLDER, filename)
        file.save(filepath)
        logger.debug(f"File saved | path={filepath}")
        
        # Recognize card (MTG only - tcg parameter no longer needed)
        with PerformanceLogger("card_recognition"):
            result = recognition_engine.recognize_card(filepath)
        
        if result['success']:
            # Save to database
            db = get_db()
            try:
                # Get card info from recognition result
                card_info = result.get('card', {})
                scryfall_id = card_info.get('id') or card_info.get('card_id') or card_info.get('scryfall_id')
                
                # Find or create the Card in the database
                existing_card = db.query(Card).filter(Card.card_id == scryfall_id).first()
                
                if not existing_card:
                    # Create new Card record
                    colors = card_info.get('colors', [])
                    if isinstance(colors, list):
                        colors = ','.join(colors)
                    
                    existing_card = Card(
                        tcg='mtg',  # Magic: The Gathering
                        card_id=scryfall_id,
                        name=card_info.get('name', 'Unknown'),
                        set_code=card_info.get('set_code', ''),
                        set_name=card_info.get('set_name', ''),
                        collector_number=card_info.get('collector_number', ''),
                        rarity=card_info.get('rarity', ''),
                        card_type=card_info.get('type_line', card_info.get('card_type', '')),
                        colors=colors,
                        mana_cost=card_info.get('mana_cost', ''),
                        image_url=card_info.get('image_url', ''),
                        oracle_text=card_info.get('oracle_text', ''),
                        artist=card_info.get('artist', ''),
                        language=card_info.get('language', 'en')
                    )
                    db.add(existing_card)
                    db.commit()
                    logger.info(f"Created new Card record | name={existing_card.name} | id={existing_card.id}")
                
                # Use the database Card ID (integer) for ScannedCard
                card_db_id = existing_card.id
                
                scanned_card = ScannedCard(
                    card_id=card_db_id,
                    confidence_score=result['confidence'],
                    image_path=filepath,
                    is_foil=request.form.get('is_foil', 'false').lower() == 'true'
                )
                db.add(scanned_card)
                db.commit()
                
                # Save price history if available
                if card_info.get('price_eur'):
                    try:
                        price_record = PriceHistory(
                            card_id=card_db_id,
                            price=float(card_info['price_eur']),
                            price_source='scryfall',
                            currency='EUR'
                        )
                        db.add(price_record)
                        db.commit()
                        logger.debug(f"EUR price saved | card_id={card_db_id} | price={card_info['price_eur']}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not save EUR price: {e}")
                
                if card_info.get('price_usd'):
                    try:
                        price_record = PriceHistory(
                            card_id=card_db_id,
                            price=float(card_info['price_usd']),
                            price_source='scryfall',
                            currency='USD'
                        )
                        db.add(price_record)
                        db.commit()
                        logger.debug(f"USD price saved | card_id={card_db_id} | price={card_info['price_usd']}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not save USD price: {e}")
                
                result['scanned_id'] = scanned_card.id
                result['card']['db_id'] = card_db_id  # Add database ID to response
                logger.info(f"Card scanned successfully | card={result['card']['name']} | scanned_id={scanned_card.id} | card_db_id={card_db_id}")
                
                # Emit real-time update
                socketio.emit('card_scanned', {
                    'card': result['card'],
                    'confidence': result['confidence'],
                    'scanned_id': scanned_card.id
                })
                
            finally:
                db.close()
        else:
            logger.info(f"Card not recognized | message={result.get('message')}")
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Scan upload error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/scan/batch', methods=['POST'])
def batch_scan():
    """Upload and recognize multiple card images"""
    logger.info("Batch scan request received")
    
    if 'files' not in request.files:
        logger.warning("Batch scan: No files provided")
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files')
    tcg = request.form.get('tcg', 'mtg')
    logger.info(f"Batch scan: Processing {len(files)} files | tcg={tcg}")
    
    results = []
    
    for file in files:
        if file and allowed_file(file.filename):
            try:
                # Save file
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{filename}"
                filepath = os.path.join(config.UPLOAD_FOLDER, filename)
                file.save(filepath)
                
                # Recognize
                with PerformanceLogger(f"batch_recognize_{file.filename}"):
                    result = recognition_engine.recognize_card(filepath, tcg)
                
                if result['success']:
                    # Save to database
                    db = get_db()
                    try:
                        scanned_card = ScannedCard(
                            card_id=result['card']['id'],
                            confidence_score=result['confidence'],
                            image_path=filepath
                        )
                        db.add(scanned_card)
                        db.commit()
                        result['scanned_id'] = scanned_card.id
                        logger.debug(f"Batch scan: Card saved | card={result['card']['name']} | scanned_id={scanned_card.id}")
                    finally:
                        db.close()
                
                results.append(result)
                
                # Emit progress
                socketio.emit('batch_progress', {
                    'current': len(results),
                    'total': len(files),
                    'latest': result
                })
                
            except Exception as e:
                logger.error(f"Batch scan error for {file.filename}: {e}", exc_info=True)
                results.append({'error': str(e), 'filename': file.filename})
    
    success_count = sum(1 for r in results if r.get('success'))
    logger.info(f"Batch scan completed | total={len(results)} | success={success_count}")
    return jsonify({'results': results, 'total': len(results)})

# ============================================================================
# CARD DATABASE ENDPOINTS
# ============================================================================

@app.route('/api/cards/search', methods=['GET'])
def search_cards():
    """Search for cards in the master database"""
    query = request.args.get('q', '')
    tcg = request.args.get('tcg')
    limit = int(request.args.get('limit', 50))
    
    logger.debug(f"Card search | query={query} | tcg={tcg} | limit={limit}")
    
    db = get_db()
    try:
        card_query = db.query(Card)
        
        if query:
            card_query = card_query.filter(Card.name.ilike(f'%{query}%'))
        if tcg:
            card_query = card_query.filter(Card.tcg == tcg)
        
        cards = card_query.limit(limit).all()
        
        logger.info(f"Card search completed | query={query} | results={len(cards)}")
        return jsonify({
            'cards': [card.to_dict() for card in cards],
            'count': len(cards)
        })
    finally:
        db.close()

@app.route('/api/cards/search/api', methods=['GET'])
def search_cards_external():
    """Search for cards using external API (Scryfall, etc.) - for manual search"""
    query = request.args.get('q', '')
    tcg = request.args.get('tcg', 'mtg')
    
    logger.debug(f"External API card search | query={query} | tcg={tcg}")
    
    if not query or len(query) < 2:
        return jsonify({'cards': [], 'count': 0})
    
    try:
        # Search using the API manager
        card_data = api_manager.search_card(query, tcg)
        
        if card_data:
            logger.info(f"External search found: {card_data.get('name')}")
            return jsonify({
                'cards': [card_data],
                'count': 1
            })
        else:
            return jsonify({'cards': [], 'count': 0})
            
    except Exception as e:
        logger.error(f"External API search error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cards/import', methods=['POST'])
def import_card_from_api():
    """Import a card from external API into database"""
    data = request.json
    name = data.get('name')
    tcg = data.get('tcg', 'mtg')
    
    logger.info(f"Card import request | name={name} | tcg={tcg}")
    
    if not name:
        logger.warning("Card import: No card name provided")
        return jsonify({'error': 'Card name required'}), 400
    
    try:
        # Search API
        with PerformanceLogger(f"api_search_{tcg}"):
            card_data = api_manager.search_card(name, tcg)
        
        if not card_data:
            logger.info(f"Card import: Card not found in API | name={name}")
            return jsonify({'error': 'Card not found in API'}), 404
        
        # Download and hash image
        image_hash = download_and_hash_card_image(card_data)
        if image_hash:
            card_data['image_hash'] = image_hash
        
        # Save to database
        db = get_db()
        try:
            # Check if card already exists
            existing = db.query(Card).filter(Card.card_id == card_data['card_id']).first()
            
            if existing:
                logger.info(f"Card already exists in database | card_id={card_data['card_id']}")
                # Add to collection even if it exists in master DB
                try:
                    scanned_card = ScannedCard(
                        card_id=existing.id,
                        image_path=existing.image_url,
                        confidence_score=1.0,
                        condition='NM',
                        quantity=1
                    )
                    db.add(scanned_card)
                    db.commit()
                    logger.info(f"Existing card added to collection | scanned_id={scanned_card.id}")
                    return jsonify({'message': 'Card added to collection (already in database)', 'card': existing.to_dict()})
                except Exception as e:
                    logger.error(f"Error adding existing card to collection: {e}")
                    return jsonify({'message': 'Card already exists', 'card': existing.to_dict()})
            
            # Extract price data if present (these are not columns in Card model)
            price_usd = card_data.pop('price_usd', None)
            price_usd_foil = card_data.pop('price_usd_foil', None)
            price_eur = card_data.pop('price_eur', None)
            price_eur_foil = card_data.pop('price_eur_foil', None)
            
            card = Card(**card_data)
            db.add(card)
            db.commit()  # Commit to get card.id
            logger.info(f"New card saved to database | card_id={card.id} | name={card.name}")
            
            # Add initial price history if available
            if price_usd:
                try:
                    price = float(price_usd)
                    price_record = PriceHistory(
                        card_id=card.id,
                        price=price,
                        price_source='api_import',
                        currency='USD'
                    )
                    db.add(price_record)
                    db.commit()
                    logger.debug(f"USD price history added | card_id={card.id} | price={price}")
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse price_usd: {price_usd}")
            
            if price_eur:
                try:
                    price = float(price_eur)
                    price_record = PriceHistory(
                        card_id=card.id,
                        price=price,
                        price_source='api_import',
                        currency='EUR'
                    )
                    db.add(price_record)
                    db.commit()
                    logger.debug(f"EUR price history added | card_id={card.id} | price={price}")
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse price_eur: {price_eur}")
            
            # Automatically add to collection (ScannedCard) so user sees it in library
            try:
                logger.debug(f"Adding card {card.id} to collection...")
                scanned_card = ScannedCard(
                    card_id=card.id,
                    image_path=card.image_url, # Use URL as path for imported cards
                    confidence_score=1.0, # Manual import is 100% confident
                    condition='NM', # Default to Near Mint
                    quantity=1
                )
                db.add(scanned_card)
                db.commit()
                logger.info(f"Card added to collection | scanned_id={scanned_card.id} | card_id={card.id}")
            except Exception as e:
                logger.error(f"Error adding to collection: {e}", exc_info=True)
                raise e # Fail the request to see the error
            
            return jsonify({'message': 'Card imported and added to collection', 'card': card.to_dict()})
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Card import error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/cards/bulk-import', methods=['POST'])
def bulk_import_cards():
    """Import multiple cards from API (e.g., entire set)"""
    data = request.json
    tcg = data.get('tcg', 'mtg')
    set_code = data.get('set_code')
    skip_hash = data.get('skip_hash', True)  # Skip image hash by default for speed
    
    logger.info(f"Bulk import request | set_code={set_code} | tcg={tcg} | skip_hash={skip_hash}")
    
    if not set_code:
        logger.warning("Bulk import: No set code provided")
        return jsonify({'error': 'Set code required'}), 400
    
    try:
        # Get total card count first for progress tracking
        total_cards = api_manager.scryfall.get_set_card_count(set_code.lower())
        if total_cards == 0:
            return jsonify({'error': f'Set not found: {set_code}'}), 404
        
        logger.info(f"Bulk import: Set {set_code} has {total_cards} cards")
        
        # Search for all cards in set
        if tcg == 'mtg':
            with PerformanceLogger(f"bulk_api_search_{set_code}"):
                cards_data = api_manager.scryfall.search_cards(f'set:{set_code}')
        else:
            logger.warning(f"Bulk import: Unsupported TCG | tcg={tcg}")
            return jsonify({'error': 'Bulk import only supported for MTG currently'}), 400
        
        db = get_db()
        imported = 0
        skipped = 0
        total = len(cards_data)
        batch_size = 50  # Commit every 50 cards for safety
        
        try:
            for idx, card_data in enumerate(cards_data):
                # Check if exists
                existing = db.query(Card).filter(Card.card_id == card_data['card_id']).first()
                
                if existing:
                    skipped += 1
                    # Emit progress for skipped cards too
                    socketio.emit('import_progress', {
                        'imported': imported,
                        'skipped': skipped,
                        'total': total,
                        'current_card': card_data.get('name', 'Unknown')
                    })
                    continue
                
                # Skip image hash download for speed (can be done later in background)
                # This makes bulk import ~10x faster
                if not skip_hash:
                    image_hash = download_and_hash_card_image(card_data)
                    if image_hash:
                        card_data['image_hash'] = image_hash
                
                # Save card name before removing price fields
                card_name = card_data.get('name', 'Unknown')
                
                # Remove price fields that are not columns in Card model
                card_data.pop('price_usd', None)
                card_data.pop('price_usd_foil', None)
                card_data.pop('price_eur', None)
                card_data.pop('price_eur_foil', None)
                
                card = Card(**card_data)
                db.add(card)
                imported += 1
                
                # Commit in batches for safety
                if imported % batch_size == 0:
                    db.commit()
                    logger.debug(f"Batch commit | imported={imported}")
                
                # Emit progress with total
                socketio.emit('import_progress', {
                    'imported': imported,
                    'skipped': skipped,
                    'total': total,
                    'current_card': card_name
                })
            
            # Final commit
            db.commit()
            logger.info(f"Bulk import completed | set={set_code} | imported={imported} | skipped={skipped}")
            
            # Start background hash download if cards were imported
            if imported > 0:
                hash_worker.start(set_code)
                logger.info(f"Started background hash download for set {set_code}")
            
            return jsonify({
                'message': f'Bulk import completed for set {set_code.upper()}. Hash download started in background.',
                'imported': imported,
                'skipped': skipped,
                'total': total,
                'hash_download_started': imported > 0
            })
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Bulk import error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# ============================================================================
# COLLECTION MANAGEMENT ENDPOINTS
# ============================================================================

@app.route('/api/collection', methods=['GET'])
def get_collection():
    """Get all scanned cards in collection, grouped by card+set"""
    collection_id = request.args.get('collection_id', type=int)
    tcg = request.args.get('tcg')
    grouped = request.args.get('grouped', 'true').lower() == 'true'
    
    logger.debug(f"Get collection request | collection_id={collection_id} | tcg={tcg} | grouped={grouped}")
    
    db = get_db()
    try:
        query = db.query(ScannedCard)
        
        if collection_id:
            query = query.filter(ScannedCard.collection_id == collection_id)
        if tcg:
            query = query.join(Card).filter(Card.tcg == tcg)
        
        scanned_cards = query.all()
        
        if grouped:
            # Group cards by name + set_name + is_foil
            grouped_cards = {}
            for sc in scanned_cards:
                card_data = sc.to_dict()
                key = f"{card_data.get('name', '')}|{card_data.get('set_name', '')}|{card_data.get('is_foil', False)}"
                
                if key in grouped_cards:
                    # Increment quantity
                    grouped_cards[key]['quantity'] += sc.quantity or 1
                    # Keep earliest scan date
                    existing_date = grouped_cards[key]['scan_date']
                    if card_data['scan_date'] < existing_date:
                        grouped_cards[key]['scan_date'] = card_data['scan_date']
                else:
                    card_data['quantity'] = sc.quantity or 1
                    grouped_cards[key] = card_data
            
            cards_list = list(grouped_cards.values())
        else:
            cards_list = [card.to_dict() for card in scanned_cards]
        
        logger.info(f"Collection retrieved | count={len(cards_list)}")
        return jsonify({
            'cards': cards_list,
            'count': len(cards_list),
            'total_cards': sum(c.get('quantity', 1) for c in cards_list)
        })
    finally:
        db.close()

@app.route('/api/collection/stats', methods=['GET'])
def get_collection_stats():
    """Get collection statistics"""
    collection_id = request.args.get('collection_id', type=int)
    
    logger.debug(f"Get collection stats | collection_id={collection_id}")
    
    db = get_db()
    try:
        query = db.query(ScannedCard)
        if collection_id:
            query = query.filter(ScannedCard.collection_id == collection_id)
        
        scanned_cards = query.all()
        
        # Calculate stats
        total_cards = sum(card.quantity for card in scanned_cards)
        unique_cards = len(scanned_cards)
        
        # TCG breakdown
        tcg_breakdown = {}
        rarity_breakdown = {}
        
        for card in scanned_cards:
            if card.card:
                tcg = card.card.tcg or 'unknown'
                tcg_breakdown[tcg] = tcg_breakdown.get(tcg, 0) + card.quantity
                
                rarity = card.card.rarity or 'unknown'
                rarity_breakdown[rarity] = rarity_breakdown.get(rarity, 0) + card.quantity
        
        # Get collection value
        value_data = price_tracker.get_collection_value(collection_id)
        
        logger.info(f"Collection stats | total={total_cards} | unique={unique_cards}")
        return jsonify({
            'total_cards': total_cards,
            'unique_cards': unique_cards,
            'tcg_breakdown': tcg_breakdown,
            'rarity_breakdown': rarity_breakdown,
            'value': value_data
        })
    finally:
        db.close()

@app.route('/api/collection/top-valuable', methods=['GET'])
def get_top_valuable_cards():
    """Get the most valuable cards in the collection"""
    limit = request.args.get('limit', 5, type=int)
    
    logger.debug(f"Get top valuable cards | limit={limit}")
    
    db = get_db()
    try:
        # Get all scanned cards with their price history
        scanned_cards = db.query(ScannedCard).all()
        
        cards_with_prices = []
        for sc in scanned_cards:
            if sc.card:
                # Get the latest EUR price
                price_eur = price_tracker.get_current_price(sc.card.id, 'EUR')
                if price_eur and price_eur > 0:
                    card_data = sc.card.to_dict()
                    card_data['price_eur'] = price_eur
                    card_data['scanned_id'] = sc.id
                    cards_with_prices.append(card_data)
        
        # Sort by price descending
        cards_with_prices.sort(key=lambda x: x.get('price_eur', 0), reverse=True)
        
        # Return top N
        top_cards = cards_with_prices[:limit]
        
        logger.info(f"Top valuable cards retrieved | count={len(top_cards)}")
        return jsonify({
            'cards': top_cards,
            'total': len(cards_with_prices)
        })
    finally:
        db.close()

# ============================================================================
# SORTING ENDPOINTS
# ============================================================================

@app.route('/api/sort/min-bins', methods=['GET'])
def get_min_bins():
    """Get minimum number of bins for each sorting criteria"""
    tcg = request.args.get('tcg', 'mtg')
    
    min_bins = {}
    for criteria in ['alphabetic', 'set', 'color', 'type', 'rarity', 'price']:
        min_bins[criteria] = sorting_engine.get_min_bins_for_criteria(criteria, tcg)
    
    return jsonify(min_bins)

@app.route('/api/sort/preview', methods=['POST'])
def preview_sorting():
    """Preview how cards will be sorted without applying"""
    data = request.json
    criteria = data.get('criteria')
    sub_criteria = data.get('sub_criteria')
    bin_count = data.get('bin_count', 6)
    collection_id = data.get('collection_id')
    
    logger.info(f"Sorting preview request | criteria={criteria} | bins={bin_count}")
    
    # Validate criteria
    valid_criteria = ['alphabetic', 'set', 'color', 'type', 'rarity', 'price']
    if criteria not in valid_criteria:
        logger.warning(f"Invalid sorting criteria: {criteria}")
        return jsonify({'error': f'Invalid criteria. Valid options: {valid_criteria}'}), 400
    
    db = get_db()
    try:
        query = db.query(ScannedCard)
        if collection_id:
            query = query.filter(ScannedCard.collection_id == collection_id)
        
        cards = query.all()
        
        # Sort cards
        with PerformanceLogger(f"sort_preview_{criteria}"):
            bins = sorting_engine.sort_cards(cards, criteria, sub_criteria, bin_count)
        
        # Get bin labels
        tcg = cards[0].card.tcg if cards and cards[0].card else 'mtg'
        labels = sorting_engine.get_bin_labels(criteria, bin_count, tcg)
        
        # Format response
        bins_data = {}
        for bin_num, bin_cards in bins.items():
            bins_data[bin_num] = {
                'label': labels.get(bin_num, f'Bin {bin_num}'),
                'count': len(bin_cards),
                'cards': [card.to_dict() for card in bin_cards[:5]]  # Preview first 5
            }
        
        logger.info(f"Sorting preview complete | total_cards={len(cards)}")
        return jsonify({
            'bins': bins_data,
            'total_cards': len(cards)
        })
        
    finally:
        db.close()

@app.route('/api/sort/apply', methods=['POST'])
def apply_sorting():
    """Apply sorting and save bin assignments"""
    data = request.json
    criteria = data.get('criteria')
    sub_criteria = data.get('sub_criteria')
    bin_count = data.get('bin_count', 6)
    collection_id = data.get('collection_id')
    save_config = data.get('save_config', False)
    config_name = data.get('config_name')
    
    logger.info(f"Apply sorting request | criteria={criteria} | bins={bin_count} | save_config={save_config}")
    
    db = get_db()
    try:
        query = db.query(ScannedCard)
        if collection_id:
            query = query.filter(ScannedCard.collection_id == collection_id)
        
        cards = query.all()
        
        # Sort cards
        with PerformanceLogger(f"sort_apply_{criteria}"):
            bins = sorting_engine.sort_cards(cards, criteria, sub_criteria, bin_count)
        
        # Save bin assignments
        db.commit()
        
        # Save configuration if requested
        if save_config and config_name:
            tcg = cards[0].card.tcg if cards and cards[0].card else None
            labels = sorting_engine.get_bin_labels(criteria, bin_count, tcg)
            
            sorting_config = SortingConfig(
                name=config_name,
                tcg=tcg,
                criteria=criteria,
                sub_criteria=sub_criteria,
                bin_count=bin_count,
                bin_mapping=labels
            )
            db.add(sorting_config)
            db.commit()
            logger.info(f"Sorting config saved | name={config_name}")
        
        # Emit completion
        socketio.emit('sorting_complete', {
            'criteria': criteria,
            'bin_count': bin_count,
            'total_cards': len(cards)
        })
        
        logger.info(f"Sorting applied | total_cards={len(cards)}")
        return jsonify({
            'message': 'Sorting applied successfully',
            'total_cards': len(cards),
            'bins': {k: len(v) for k, v in bins.items()}
        })
        
    finally:
        db.close()

# ============================================================================
# PRICE TRACKING ENDPOINTS
# ============================================================================

@app.route('/api/prices/update', methods=['POST'])
def update_prices():
    """Update prices for all cards or specific TCG"""
    data = request.json
    tcg = data.get('tcg')
    max_cards = data.get('max_cards', 100)
    
    logger.info(f"Price update request | tcg={tcg} | max_cards={max_cards}")
    
    try:
        with PerformanceLogger("price_update"):
            stats = price_tracker.update_all_prices(tcg, max_cards)
        logger.info(f"Price update complete | stats={stats}")
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Price update error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/prices/history/<int:card_id>', methods=['GET'])
def get_price_history(card_id):
    """Get price history for a card"""
    days = request.args.get('days', 30, type=int)
    
    logger.debug(f"Price history request | card_id={card_id} | days={days}")
    
    try:
        history = price_tracker.get_card_price_history(card_id, days)
        logger.info(f"Price history retrieved | card_id={card_id} | records={len(history)}")
        return jsonify({'history': history})
    except Exception as e:
        logger.error(f"Price history error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/prices/trend/<int:card_id>', methods=['GET'])
def get_price_trend(card_id):
    """Get price trend for a card"""
    days = request.args.get('days', 7, type=int)
    
    logger.debug(f"Price trend request | card_id={card_id} | days={days}")
    
    try:
        trend = price_tracker.get_price_trend(card_id, days)
        logger.info(f"Price trend retrieved | card_id={card_id} | trend={trend['trend']}")
        return jsonify(trend)
    except Exception as e:
        logger.error(f"Price trend error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/prices/scheduler/status', methods=['GET'])
def get_scheduler_status():
    """Get price update scheduler status"""
    return jsonify(price_scheduler.get_status())

@app.route('/api/prices/scheduler/start', methods=['POST'])
def start_scheduler():
    """Start the price update scheduler"""
    price_scheduler.start()
    return jsonify({'message': 'Scheduler started', 'status': price_scheduler.get_status()})

@app.route('/api/prices/scheduler/stop', methods=['POST'])
def stop_scheduler():
    """Stop the price update scheduler"""
    price_scheduler.stop()
    return jsonify({'message': 'Scheduler stopped', 'status': price_scheduler.get_status()})

# ============================================================================
# HASH DOWNLOAD ENDPOINTS
# ============================================================================

@app.route('/api/hash/status', methods=['GET'])
def get_hash_status():
    """Get hash download worker status"""
    return jsonify(hash_worker.get_status())

@app.route('/api/hash/start', methods=['POST'])
def start_hash_download():
    """Start hash download for cards without hash"""
    data = request.json or {}
    set_code = data.get('set_code')
    
    if hash_worker.start(set_code):
        return jsonify({'message': 'Hash download started', 'status': hash_worker.get_status()})
    else:
        return jsonify({'error': 'Hash download already running', 'status': hash_worker.get_status()}), 400

@app.route('/api/hash/stop', methods=['POST'])
def stop_hash_download():
    """Stop hash download"""
    hash_worker.stop()
    return jsonify({'message': 'Hash download stopped', 'status': hash_worker.get_status()})

@app.route('/api/hash/pending', methods=['GET'])
def get_pending_hashes():
    """Get count of cards without image hash"""
    set_code = request.args.get('set_code')
    
    db = get_db()
    try:
        query = db.query(Card).filter(Card.image_hash == None)
        if set_code:
            query = query.filter(Card.set_code == set_code.lower())
        
        count = query.count()
        return jsonify({'pending': count, 'set_code': set_code})
    finally:
        db.close()

@app.route('/api/prices/trending', methods=['GET'])
def get_trending_cards():
    """Get cards with biggest price changes (up and down)"""
    limit = request.args.get('limit', 5, type=int)
    days = request.args.get('days', 7, type=int)
    
    logger.debug(f"Trending cards request | limit={limit} | days={days}")
    
    db = get_db()
    try:
        from sqlalchemy.orm import joinedload
        
        # Get all scanned cards with their card info
        scanned_cards = db.query(ScannedCard).options(
            joinedload(ScannedCard.card)
        ).all()
        
        trending_data = []
        
        for sc in scanned_cards:
            if not sc.card:
                continue
            
            trend = price_tracker.get_price_trend(sc.card.id, days)
            
            if trend['data_points'] >= 2:
                trending_data.append({
                    'id': sc.id,
                    'card_id': sc.card.id,
                    'name': sc.card.name,
                    'set_name': sc.card.set_name,
                    'image_url': sc.card.image_url,
                    'current_price': trend['current_price'],
                    'previous_price': trend['previous_price'],
                    'change_amount': trend['change_amount'],
                    'change_percent': trend['change_percent'],
                    'trend': trend['trend'],
                    'trend_icon': trend['trend_icon']
                })
        
        # Sort by absolute change percentage
        trending_data.sort(key=lambda x: abs(x['change_percent']), reverse=True)
        
        # Split into gainers and losers
        gainers = [c for c in trending_data if c['trend'] == 'up'][:limit]
        losers = [c for c in trending_data if c['trend'] == 'down'][:limit]
        
        logger.info(f"Trending cards retrieved | gainers={len(gainers)} | losers={len(losers)}")
        
        return jsonify({
            'gainers': gainers,
            'losers': losers,
            'total_tracked': len(trending_data)
        })
        
    except Exception as e:
        logger.error(f"Trending cards error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

# ============================================================================
# STATIC FILE SERVING
# ============================================================================

@app.route('/')
def index():
    """Serve main page"""
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory('static', path)

# ============================================================================
# WEBSOCKET EVENTS
# ============================================================================

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info("WebSocket client connected")
    emit('connected', {'message': 'Connected to TCG Scan server'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info("WebSocket client disconnected")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("TCG Scan Server Starting")
    logger.info("=" * 60)
    logger.info(f"Server starting on http://localhost:5000")
    logger.info(f"Database: {config.DATABASE_PATH}")
    logger.info(f"Upload folder: {config.UPLOAD_FOLDER}")
    logger.info("=" * 60)
    
    # Start background price update scheduler
    price_scheduler.start()
    logger.info("Price update scheduler started (updates every 6 hours)")
    
    socketio.run(app, debug=config.DEBUG, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
