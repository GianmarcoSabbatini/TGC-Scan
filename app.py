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
        
        # Get TCG from request
        tcg = request.form.get('tcg', 'mtg')
        
        # Recognize card
        with PerformanceLogger("card_recognition"):
            result = recognition_engine.recognize_card(filepath, tcg)
        
        if result['success']:
            # Save to database
            db = get_db()
            try:
                scanned_card = ScannedCard(
                    card_id=result['card']['id'],
                    confidence_score=result['confidence'],
                    image_path=filepath,
                    is_foil=request.form.get('is_foil', 'false').lower() == 'true'
                )
                db.add(scanned_card)
                db.commit()
                
                # Save price history if available
                card_info = result.get('card', {})
                card_db_id = result['card']['id']
                
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
                logger.info(f"Card scanned successfully | card={result['card']['name']} | scanned_id={scanned_card.id}")
                
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
            
            # Extract price data if present
            price_usd = card_data.pop('price_usd', None)
            price_usd_foil = card_data.pop('price_usd_foil', None)
            
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
                    logger.debug(f"Price history added | card_id={card.id} | price={price}")
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse price_usd: {price_usd}")
            
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
    
    logger.info(f"Bulk import request | set_code={set_code} | tcg={tcg}")
    
    if not set_code:
        logger.warning("Bulk import: No set code provided")
        return jsonify({'error': 'Set code required'}), 400
    
    try:
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
        
        try:
            for card_data in cards_data:
                # Check if exists
                existing = db.query(Card).filter(Card.card_id == card_data['card_id']).first()
                
                if existing:
                    skipped += 1
                    continue
                
                # Download and hash image
                image_hash = download_and_hash_card_image(card_data)
                if image_hash:
                    card_data['image_hash'] = image_hash
                
                card = Card(**card_data)
                db.add(card)
                imported += 1
                
                # Emit progress
                socketio.emit('import_progress', {
                    'imported': imported,
                    'skipped': skipped,
                    'current_card': card_data['name']
                })
            
            db.commit()
            logger.info(f"Bulk import completed | set={set_code} | imported={imported} | skipped={skipped}")
            
            return jsonify({
                'message': 'Bulk import completed',
                'imported': imported,
                'skipped': skipped
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

# ============================================================================
# SORTING ENDPOINTS
# ============================================================================

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
    
    socketio.run(app, debug=config.DEBUG, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
