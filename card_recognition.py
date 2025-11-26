"""
TCG Scan - Card Recognition Engine
Uses OCR + API search for card recognition from photos
"""
import cv2
import numpy as np
from PIL import Image
import imagehash
import requests
import os
from typing import Optional, Tuple, List, Dict
import config
from database import Card, get_db
from logger import get_logger, PerformanceLogger
import re

# Try to import pytesseract for OCR
try:
    import pytesseract
    # Windows: set path to tesseract executable
    import shutil
    tesseract_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        r'C:\Users\Utente\AppData\Local\Programs\Tesseract-OCR\tesseract.exe',
    ]
    
    # Try to find tesseract
    tesseract_found = shutil.which('tesseract')
    if tesseract_found:
        pytesseract.pytesseract.tesseract_cmd = tesseract_found
        TESSERACT_AVAILABLE = True
    else:
        for path in tesseract_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                TESSERACT_AVAILABLE = True
                break
        else:
            TESSERACT_AVAILABLE = False
            
except ImportError:
    TESSERACT_AVAILABLE = False

# Initialize logger for this module
logger = get_logger('recognition')

class CardRecognitionEngine:
    """Main card recognition engine using OCR and API search"""
    
    def __init__(self):
        self.hash_threshold = config.RECOGNITION_CONFIDENCE_THRESHOLD
        # Import API integrations
        from api_integrations import ScryfallAPI, PokemonTCGAPI, YuGiOhAPI
        self.scryfall_api = ScryfallAPI()
        self.pokemon_api = PokemonTCGAPI()
        self.yugioh_api = YuGiOhAPI()
        logger.info("CardRecognitionEngine initialized")
        
    def preprocess_image(self, image_path: str) -> Tuple[np.ndarray, Image.Image]:
        """
        Preprocess scanned card image
        - Auto-rotate if needed
        - Crop to card boundaries
        - Enhance contrast
        """
        logger.debug(f"Preprocessing image: {image_path}")
        
        # Load image
        img = cv2.imread(image_path)
        if img is None:
            logger.error(f"Could not load image: {image_path}")
            raise ValueError(f"Could not load image: {image_path}")
        
        logger.debug(f"Original image size: {img.shape}")
        
        # Convert to grayscale for processing
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Edge detection with adjusted thresholds for mobile photos
        edges = cv2.Canny(blurred, 30, 100)
        
        # Dilate edges to connect nearby edges
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=2)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Find the largest rectangular contour (the card)
        card_contour = None
        max_area = 0
        img_area = img.shape[0] * img.shape[1]
        
        logger.debug(f"Found {len(contours)} contours")
        
        for contour in contours:
            area = cv2.contourArea(contour)
            # Card should be at least 10% of image and at most 95%
            if area > img_area * 0.1 and area < img_area * 0.95:
                # Approximate the contour to a polygon
                peri = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
                
                # If it's roughly rectangular (4 corners) or close to it
                if len(approx) >= 4 and len(approx) <= 6 and area > max_area:
                    max_area = area
                    card_contour = approx
        
        # Crop to card if found, otherwise try center crop
        if card_contour is not None:
            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(card_contour)
            cropped = img[y:y+h, x:x+w]
            logger.info(f"Card detected: x={x}, y={y}, w={w}, h={h}")
        else:
            # No card detected - assume card is centered, crop to middle 70%
            h, w = img.shape[:2]
            margin_x = int(w * 0.15)
            margin_y = int(h * 0.15)
            cropped = img[margin_y:h-margin_y, margin_x:w-margin_x]
            logger.warning(f"No card contour detected, using center crop")
        
        # Enhance contrast
        lab = cv2.cvtColor(cropped, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        enhanced = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
        
        logger.debug(f"Cropped image size: {enhanced.shape}")
        
        # Convert to PIL Image for hashing
        pil_img = Image.fromarray(cv2.cvtColor(enhanced, cv2.COLOR_BGR2RGB))
        
        return enhanced, pil_img
    
    def extract_card_name_region(self, image: np.ndarray) -> np.ndarray:
        """
        Extract the card name region from the image.
        MTG cards have the name in the top portion, with a specific layout.
        Standard MTG card ratio is about 63:88 (width:height) = 0.716
        """
        h, w = image.shape[:2]
        aspect_ratio = w / h
        
        logger.debug(f"Extracting name region | size={w}x{h} | aspect_ratio={aspect_ratio:.3f}")
        
        # Check if image is in portrait orientation (card-like)
        if aspect_ratio < 0.9:  # Portrait - card is vertical
            # MTG card name is in the top area, about 4-12% from top
            top_margin = int(h * 0.04)
            bottom_cut = int(h * 0.13)
            left_margin = int(w * 0.06)
            right_cut = int(w * 0.85)
        elif aspect_ratio > 1.1:  # Landscape - card might be horizontal
            # Card is rotated 90 degrees
            top_margin = int(h * 0.06)
            bottom_cut = int(h * 0.85)
            left_margin = int(w * 0.04)
            right_cut = int(w * 0.13)
        else:  # Square-ish - try standard portrait extraction
            top_margin = int(h * 0.04)
            bottom_cut = int(h * 0.15)
            left_margin = int(w * 0.05)
            right_cut = int(w * 0.80)
        
        name_region = image[top_margin:bottom_cut, left_margin:right_cut]
        
        logger.debug(f"Name region extracted | size={name_region.shape[1]}x{name_region.shape[0]}")
        
        # DON'T resize too small - Tesseract needs good resolution
        # Keep at least 600px width for better OCR
        target_width = 600
        if name_region.shape[1] < target_width:
            scale = target_width / name_region.shape[1]
            name_region = cv2.resize(name_region, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        elif name_region.shape[1] > 1200:
            # Too big, scale down a bit
            scale = 800 / name_region.shape[1]
            name_region = cv2.resize(name_region, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        
        logger.debug(f"Name region after resize: {name_region.shape[1]}x{name_region.shape[0]}")
        
        # Convert to grayscale
        gray = cv2.cvtColor(name_region, cv2.COLOR_BGR2GRAY)
        
        # Simple preprocessing - just denoise slightly
        # Don't over-process!
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        
        return gray
    
    def extract_text_ocr(self, image: np.ndarray) -> str:
        """Extract text from image using Tesseract OCR"""
        if not TESSERACT_AVAILABLE:
            logger.warning("Tesseract not available")
            return ""
        
        try:
            # Convert to PIL for pytesseract
            pil_img = Image.fromarray(image)
            
            # Use simpler config - let Tesseract do its thing
            # PSM 7 = single line, PSM 6 = block
            configs = [
                r'--oem 3 --psm 7 -l eng',   # Single line, English
                r'--oem 3 --psm 6 -l eng',   # Block of text, English
            ]
            
            best_text = ""
            best_score = 0
            
            for config in configs:
                try:
                    text = pytesseract.image_to_string(pil_img, config=config)
                    
                    # Clean up the text
                    text = text.strip()
                    # Remove non-printable chars but keep letters, numbers, spaces, common punctuation
                    text = re.sub(r'[^a-zA-Z0-9\s\'-,]', '', text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    
                    # Score based on: length and ratio of actual letters
                    if len(text) >= 3:
                        letter_count = sum(c.isalpha() for c in text)
                        letter_ratio = letter_count / len(text) if text else 0
                        
                        # Good text should be mostly letters with some spaces
                        if letter_ratio > 0.6:
                            score = letter_count
                            if score > best_score:
                                best_score = score
                                best_text = text
                except Exception as e:
                    logger.warning(f"OCR config failed: {config} - {e}")
                    continue
            
            logger.info(f"OCR extracted text: '{best_text}'")
            return best_text
        except Exception as e:
            logger.error(f"OCR error: {e}")
            return ""
    
    def search_card_by_name(self, card_name: str, tcg: str = 'mtg') -> Optional[Dict]:
        """
        Search for a card by name using the appropriate API.
        Returns card data dict or None.
        """
        if not card_name or len(card_name) < 2:
            return None
        
        logger.debug(f"Searching card by name: '{card_name}' | tcg={tcg}")
        
        try:
            if tcg == 'mtg':
                result = self.scryfall_api.search_card_by_name(card_name)
            elif tcg == 'pokemon':
                result = self.pokemon_api.search_card_by_name(card_name)
            elif tcg == 'yugioh':
                result = self.yugioh_api.search_card_by_name(card_name)
            else:
                result = self.scryfall_api.search_card_by_name(card_name)
            
            if result:
                logger.info(f"Found card via API: {result.get('name')}")
                return result
            
        except Exception as e:
            logger.error(f"API search error: {e}")
        
        return None

    def recognize_from_photo(self, image_path: str, tcg: str = 'mtg') -> Dict:
        """
        Main recognition method for mobile photos.
        Uses OCR to extract card name, then searches via API.
        """
        logger.info(f"Recognizing card from photo | path={image_path} | tcg={tcg}")
        
        try:
            # Load and preprocess image
            processed_img, pil_img = self.preprocess_image(image_path)
            
            # Save debug images
            debug_dir = os.path.join(os.path.dirname(image_path), 'debug')
            os.makedirs(debug_dir, exist_ok=True)
            
            # Save the processed/cropped card image
            debug_card_path = os.path.join(debug_dir, 'processed_card.png')
            cv2.imwrite(debug_card_path, processed_img)
            logger.info(f"Saved processed card debug image: {debug_card_path}")
            
            # Try OCR if available
            if TESSERACT_AVAILABLE:
                # Extract name region
                name_region = self.extract_card_name_region(processed_img)
                
                # Save debug image
                debug_path = os.path.join(debug_dir, 'name_region.png')
                cv2.imwrite(debug_path, name_region)
                logger.info(f"Saved name region debug image: {debug_path}")
                
                # OCR the name
                extracted_name = self.extract_text_ocr(name_region)
                
                if extracted_name and len(extracted_name) >= 3:
                    # Search by extracted name
                    card_data = self.search_card_by_name(extracted_name, tcg)
                    
                    if card_data:
                        return {
                            'success': True,
                            'card': card_data,
                            'confidence': 0.85,  # OCR match
                            'method': 'ocr',
                            'extracted_name': extracted_name,
                            'message': f"Card recognized via OCR: {card_data.get('name')}"
                        }
                    
                    # Try fuzzy search with partial name
                    words = extracted_name.split()
                    if len(words) >= 1:
                        for i in range(len(words), 0, -1):
                            partial_name = ' '.join(words[:i])
                            if len(partial_name) >= 3:
                                card_data = self.search_card_by_name(partial_name, tcg)
                                if card_data:
                                    return {
                                        'success': True,
                                        'card': card_data,
                                        'confidence': 0.70,
                                        'method': 'ocr_partial',
                                        'extracted_name': extracted_name,
                                        'message': f"Card recognized via partial OCR: {card_data.get('name')}"
                                    }
            
            # Fallback: compute hash for future matching
            img_hash = self.compute_image_hash(pil_img)
            
            return {
                'success': False,
                'card': None,
                'confidence': 0.0,
                'method': 'ocr_failed',
                'image_hash': img_hash,
                'message': 'Could not recognize card. Try entering the name manually.'
            }
            
        except Exception as e:
            logger.error(f"Recognition from photo failed: {e}", exc_info=True)
            return {
                'success': False,
                'card': None,
                'confidence': 0.0,
                'error': str(e),
                'message': f'Recognition error: {str(e)}'
            }

    def compute_image_hash(self, pil_image: Image.Image) -> str:
        """Compute perceptual hash of card image"""
        # Use average hash (fast and effective for card recognition)
        ahash = imagehash.average_hash(pil_image, hash_size=16)
        return str(ahash)
    
    def find_matching_card(self, image_hash: str, tcg: str = None) -> Optional[Tuple[Card, float]]:
        """
        Find matching card in database using perceptual hash
        Returns (Card, confidence_score) or None
        """
        logger.debug(f"Searching for matching card | hash={image_hash[:16]}... | tcg={tcg}")
        db = get_db()
        
        try:
            with PerformanceLogger("find_matching_card"):
                # Query cards from database
                query = db.query(Card)
                if tcg:
                    query = query.filter(Card.tcg == tcg)
                
                cards = query.all()
                logger.debug(f"Comparing against {len(cards)} cards in database")
                
                best_match = None
                best_score = 0
                
                # Compare hashes
                query_hash = imagehash.hex_to_hash(image_hash)
                
                for card in cards:
                    if not card.image_hash:
                        continue
                    
                    try:
                        card_hash = imagehash.hex_to_hash(card.image_hash)
                        # Calculate Hamming distance
                        distance = query_hash - card_hash
                        
                        # Convert distance to confidence score (0-1)
                        # Lower distance = higher confidence
                        max_distance = config.IMAGE_HASH_THRESHOLD
                        if distance <= max_distance:
                            confidence = 1.0 - (distance / max_distance)
                            if confidence > best_score:
                                best_score = confidence
                                best_match = card
                    except Exception as e:
                        logger.warning(f"Error comparing hash for card {card.name}: {e}")
                        continue
                
                if best_match and best_score >= config.RECOGNITION_CONFIDENCE_THRESHOLD:
                    logger.info(f"Card matched: {best_match.name} | confidence={best_score:.2%}")
                    return (best_match, best_score)
                
                logger.debug("No matching card found above confidence threshold")
                return None
            
        finally:
            db.close()
    
    def recognize_card(self, image_path: str, tcg: str = None) -> Dict:
        """
        Main recognition pipeline - tries multiple methods:
        1. OCR + API search (best for mobile photos)
        2. Hash matching against local database
        """
        logger.info(f"Starting card recognition | path={image_path} | tcg={tcg}")
        
        tcg = tcg or 'mtg'
        
        try:
            with PerformanceLogger("recognize_card"):
                # Preprocess image
                processed_img, pil_img = self.preprocess_image(image_path)
                
                # Save debug images
                debug_dir = os.path.join(os.path.dirname(image_path), 'debug')
                os.makedirs(debug_dir, exist_ok=True)
                
                debug_processed = os.path.join(debug_dir, 'processed_card.png')
                cv2.imwrite(debug_processed, processed_img)
                logger.info(f"Saved processed card: {debug_processed} | shape={processed_img.shape}")
                
                # Method 1: Try OCR + API search first
                if TESSERACT_AVAILABLE:
                    logger.debug("Trying OCR recognition...")
                    
                    # First, save the raw name region (before preprocessing) for debug
                    h, w = processed_img.shape[:2]
                    aspect_ratio = w / h
                    if aspect_ratio < 0.9:
                        top_m, bottom_c, left_m, right_c = int(h*0.04), int(h*0.13), int(w*0.06), int(w*0.85)
                    else:
                        top_m, bottom_c, left_m, right_c = int(h*0.04), int(h*0.15), int(w*0.05), int(w*0.80)
                    raw_name_region = processed_img[top_m:bottom_c, left_m:right_c]
                    debug_name_raw = os.path.join(debug_dir, 'name_region_raw.png')
                    cv2.imwrite(debug_name_raw, raw_name_region)
                    logger.info(f"Saved raw name region: {debug_name_raw}")
                    
                    name_region = self.extract_card_name_region(processed_img)
                    
                    # Save debug name region
                    debug_name = os.path.join(debug_dir, 'name_region.png')
                    cv2.imwrite(debug_name, name_region)
                    logger.info(f"Saved name region: {debug_name} | shape={name_region.shape}")
                    
                    extracted_name = self.extract_text_ocr(name_region)
                    
                    if extracted_name and len(extracted_name) >= 3:
                        card_data = self.search_card_by_name(extracted_name, tcg)
                        if card_data:
                            logger.info(f"Recognition via OCR successful: {card_data.get('name')}")
                            return {
                                'success': True,
                                'card': card_data,
                                'confidence': 0.85,
                                'method': 'ocr_api',
                                'extracted_name': extracted_name,
                                'message': f"Card recognized: {card_data.get('name')}"
                            }
                
                # Method 2: Direct API search with fuzzy matching
                # Try searching API directly (Scryfall has good fuzzy matching)
                logger.debug("Trying direct API search...")
                card_data = self.search_card_by_name_fuzzy(image_path, tcg)
                if card_data:
                    return {
                        'success': True,
                        'card': card_data,
                        'confidence': 0.90,
                        'method': 'api_search',
                        'message': f"Card recognized: {card_data.get('name')}"
                    }
                
                # Method 3: Hash matching against local database
                logger.debug("Trying hash matching...")
                img_hash = self.compute_image_hash(pil_img)
                match = self.find_matching_card(img_hash, tcg)
                
                if match:
                    card, confidence = match
                    logger.info(f"Recognition via hash | card={card.name} | confidence={confidence:.2%}")
                    return {
                        'success': True,
                        'card': card.to_dict(),
                        'confidence': confidence,
                        'method': 'hash',
                        'image_hash': img_hash,
                        'message': f'Card recognized: {card.name}'
                    }
                
                # No match found
                logger.info("Recognition complete - no match found")
                return {
                    'success': False,
                    'card': None,
                    'confidence': 0.0,
                    'image_hash': img_hash if 'img_hash' in dir() else None,
                    'message': 'No matching card found. Try entering the name manually.'
                }
                
        except Exception as e:
            logger.error(f"Recognition failed: {e}", exc_info=True)
            return {
                'success': False,
                'card': None,
                'confidence': 0.0,
                'error': str(e),
                'message': f'Recognition error: {str(e)}'
            }
    
    def search_card_by_name_fuzzy(self, image_path: str, tcg: str) -> Optional[Dict]:
        """
        Try to recognize card by sending image name hints to API.
        This is a placeholder for more advanced recognition.
        """
        # For now, return None - this would need a cloud vision API
        return None
    
    def batch_recognize(self, image_paths: List[str], tcg: str = None) -> List[Dict]:
        """Recognize multiple cards in batch"""
        results = []
        for image_path in image_paths:
            result = self.recognize_card(image_path, tcg)
            results.append(result)
        return results

def download_and_hash_card_image(card_data: Dict) -> Optional[str]:
    """
    Download card image from URL and compute its hash
    Used when populating the database with card data
    """
    from io import BytesIO
    
    image_url = card_data.get('image_url')
    if not image_url:
        return None
    
    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            ahash = imagehash.average_hash(img, hash_size=16)
            return str(ahash)
    except Exception as e:
        logger.error(f"Error downloading/hashing image: {e}")
    
    return None
