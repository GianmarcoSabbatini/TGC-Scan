"""
TCG Scan - Card Recognition Engine
Uses OCR + API search for card recognition from photos.
Now includes fuzzy matching (SymSpell) to correct OCR errors.
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

# Import fuzzy matcher for OCR error correction
try:
    from fuzzy_matcher import FuzzyCardMatcher, fuzzy_search_card, fuzzy_search_with_confidence
    FUZZY_MATCHER_AVAILABLE = True
    print("[OCR] Fuzzy matcher loaded successfully")
except ImportError as e:
    FUZZY_MATCHER_AVAILABLE = False
    print(f"[OCR] Fuzzy matcher not available: {e}")

# Try to import pytesseract for OCR
try:
    import pytesseract
    # Windows: set path to tesseract executable
    import shutil
    tesseract_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        r'C:\Users\Utente\AppData\Local\Programs\Tesseract-OCR\tesseract.exe',
        r'C:\Users\Gianmarco\AppData\Local\Programs\Tesseract-OCR\tesseract.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe'),
        os.path.expandvars(r'%PROGRAMFILES%\Tesseract-OCR\tesseract.exe'),
    ]
    
    # Try to find tesseract
    tesseract_found = shutil.which('tesseract')
    if tesseract_found:
        pytesseract.pytesseract.tesseract_cmd = tesseract_found
        TESSERACT_AVAILABLE = True
        print(f"[OCR] Tesseract found via PATH: {tesseract_found}")
    else:
        for path in tesseract_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                TESSERACT_AVAILABLE = True
                print(f"[OCR] Tesseract found at: {path}")
                break
        else:
            TESSERACT_AVAILABLE = False
            print("[OCR] Tesseract NOT found - OCR disabled")
            
except ImportError:
    TESSERACT_AVAILABLE = False
    print("[OCR] pytesseract not installed - OCR disabled")

# Initialize logger for this module
logger = get_logger('recognition')

class CardRecognitionEngine:
    """Main card recognition engine using OCR and API search"""
    
    def __init__(self):
        self.hash_threshold = config.RECOGNITION_CONFIDENCE_THRESHOLD
        # Import API integrations
        from api_integrations import ScryfallAPI
        self.scryfall_api = ScryfallAPI()
        
        # Initialize fuzzy matcher for OCR error correction
        self.fuzzy_matcher = None
        if FUZZY_MATCHER_AVAILABLE:
            try:
                self.fuzzy_matcher = FuzzyCardMatcher()
                logger.info("Fuzzy matcher initialized for OCR error correction")
            except Exception as e:
                logger.warning(f"Could not initialize fuzzy matcher: {e}")
        
        logger.info("CardRecognitionEngine initialized")
        
    def preprocess_image(self, image_path: str) -> Tuple[np.ndarray, Image.Image, np.ndarray]:
        """
        Preprocess scanned card image
        - Auto-rotate if needed
        - Crop to card boundaries
        - Enhance contrast
        
        Returns:
            Tuple of (processed_image, pil_image, original_image)
        """
        logger.debug(f"Preprocessing image: {image_path}")
        
        # Load image
        img = cv2.imread(image_path)
        if img is None:
            logger.error(f"Could not load image: {image_path}")
            raise ValueError(f"Could not load image: {image_path}")
        
        # Keep a copy of the original before any processing
        original_img = img.copy()
        
        logger.debug(f"Original image size: {img.shape}")
        
        # Convert to grayscale for processing
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Try multiple edge detection strategies
        card_contour = None
        max_area = 0
        img_area = img.shape[0] * img.shape[1]
        
        # Strategy 1: Standard Canny edge detection
        edges = cv2.Canny(blurred, 30, 100)
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=2)
        
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        logger.debug(f"Found {len(contours)} contours with standard edge detection")
        
        for contour in contours:
            area = cv2.contourArea(contour)
            # Card should be at least 5% of image and at most 95%
            if area > img_area * 0.05 and area < img_area * 0.95:
                peri = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
                
                # Accept polygons with 4-8 vertices (cards may have rounded corners)
                if len(approx) >= 4 and len(approx) <= 8 and area > max_area:
                    # Check aspect ratio is card-like (between 0.5 and 0.9)
                    x, y, w, h = cv2.boundingRect(approx)
                    aspect = w / h if h > 0 else 0
                    if 0.5 < aspect < 0.9 or 0.5 < (1/aspect) < 0.9:
                        max_area = area
                        card_contour = approx
        
        # Strategy 2: If no card found, try adaptive threshold
        if card_contour is None:
            adaptive = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            contours2, _ = cv2.findContours(adaptive, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            logger.debug(f"Trying adaptive threshold: {len(contours2)} contours")
            
            for contour in contours2:
                area = cv2.contourArea(contour)
                if area > img_area * 0.05 and area < img_area * 0.95:
                    peri = cv2.arcLength(contour, True)
                    approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
                    if len(approx) >= 4 and len(approx) <= 8 and area > max_area:
                        x, y, w, h = cv2.boundingRect(approx)
                        aspect = w / h if h > 0 else 0
                        if 0.5 < aspect < 0.9 or 0.5 < (1/aspect) < 0.9:
                            max_area = area
                            card_contour = approx
        
        # Crop to card if found, otherwise try center crop
        if card_contour is not None:
            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(card_contour)
            cropped = img[y:y+h, x:x+w]
            logger.info(f"Card detected: x={x}, y={y}, w={w}, h={h}")
        else:
            # No card detected - use smarter center crop
            # The card should be roughly in the center of the camera frame
            # MTG card aspect ratio is ~0.716 (63:88)
            h, w = img.shape[:2]
            
            # For portrait images (phone held vertically), the card is vertical
            # For landscape images, the card might be horizontal
            if h > w:  # Portrait orientation
                # Card should occupy roughly 60-70% of the frame width
                # and be vertically centered
                card_width = int(w * 0.65)
                card_height = int(card_width / 0.716)  # MTG aspect ratio
                
                # Center the crop
                margin_x = (w - card_width) // 2
                margin_y = (h - card_height) // 2
                
                # Make sure we don't go out of bounds
                margin_y = max(0, margin_y)
                end_y = min(h, margin_y + card_height)
                
                cropped = img[margin_y:end_y, margin_x:margin_x+card_width]
                logger.warning(f"No card contour detected, using smart center crop (portrait) | margins=({margin_x}, {margin_y})")
            else:  # Landscape orientation
                # Less common, but handle it
                margin_x = int(w * 0.15)
                margin_y = int(h * 0.10)
                cropped = img[margin_y:h-margin_y, margin_x:w-margin_x]
                logger.warning(f"No card contour detected, using center crop (landscape)")
        
        # Enhance contrast
        lab = cv2.cvtColor(cropped, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        enhanced = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
        
        # Auto-rotate if the cropped card is in landscape orientation
        # MTG cards should be portrait (taller than wide)
        ch, cw = enhanced.shape[:2]
        if cw > ch:  # Landscape - card is rotated
            logger.info(f"Cropped card is landscape ({cw}x{ch}), rotating to portrait")
            enhanced = cv2.rotate(enhanced, cv2.ROTATE_90_COUNTERCLOCKWISE)
        
        logger.debug(f"Cropped image size: {enhanced.shape}")
        
        # Convert to PIL Image for hashing
        pil_img = Image.fromarray(cv2.cvtColor(enhanced, cv2.COLOR_BGR2RGB))
        
        return enhanced, pil_img, original_img
    
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
        # If image is landscape (wider than tall), rotate it to portrait
        if aspect_ratio > 1.1:
            logger.debug(f"Landscape image detected (aspect={aspect_ratio:.3f}), rotating 90 degrees")
            image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
            h, w = image.shape[:2]
            aspect_ratio = w / h
            logger.debug(f"After rotation: {w}x{h}, aspect={aspect_ratio:.3f}")
        
        if aspect_ratio < 0.9:  # Portrait - card is vertical
            # MTG card name is in the top area, about 3-10% from top
            # Based on testing: 3-10% vertical, 5-70% horizontal works best
            top_margin = int(h * 0.03)
            bottom_cut = int(h * 0.10)
            left_margin = int(w * 0.05)
            right_cut = int(w * 0.70)
        else:  # Square-ish or still landscape after rotation - try standard extraction
            top_margin = int(h * 0.03)
            bottom_cut = int(h * 0.10)
            left_margin = int(w * 0.05)
            right_cut = int(w * 0.70)
        
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
    
    def extract_set_info_from_full_image(self, image: np.ndarray) -> Dict[str, str]:
        """
        Extract set code and collector number from the bottom-left corner of the card.
        
        The set info on MTG cards appears in a very specific location:
        - Bottom-left corner: last 5-7% of card height, first 30-35% of width
        - Format: collector number (e.g., "168") on first line
                  set code + language (e.g., "WOE · EN") on second line
        
        We scan a small region and look for patterns like:
        - 2-4 digit numbers (collector number)
        - Known 3-letter set codes near the number
        """
        if not TESSERACT_AVAILABLE:
            logger.warning("Tesseract not available for set info extraction")
            return {'set_code': None, 'collector_number': None}
        
        h, w = image.shape[:2]
        
        # Save debug image
        debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', 'debug')
        os.makedirs(debug_dir, exist_ok=True)
        
        # Known MTG set codes (most common/recent ones)
        known_sets = {
            'FIN', 'MKM', 'WOE', 'LCI', 'MOM', 'ONE', 'BRO', 'DMU', 'SNC', 'NEO',
            'VOW', 'MID', 'AFR', 'STX', 'KHM', 'ZNR', 'IKO', 'THB', 'ELD', 'WAR',
            'RNA', 'GRN', 'DOM', 'RIX', 'XLN', 'HOU', 'AKH', 'AER', 'KLD', 'EMN',
            'SOI', 'OGW', 'BFZ', 'DTK', 'FRF', 'KTK', 'M21', 'M20', 'M19', 'M15',
            'DSK', 'BLB', 'OTJ', 'MKC', 'CLU', 'PIP', 'ACR', 'WHO', 'LTR', 'CMM',
            'WOT', '2X2', 'CLB', 'NCC', 'SLD', 'J22', 'UNF', 'DMC', 'MUL', 'BRC',
            'BOT', 'BRR', 'ONC', 'MOM', 'MAT', 'MUL', 'LCC', 'RVR', 'SPG', 'PIO',
            'FDN', 'DSC', 'MH3', 'MH2', 'MH1', '40K', 'REX', '30A',
            # Spider-Man and Marvel sets
            'SPM', 'PSPM', 'TSPM', 'OM1'
        }
        
        best_result = {'set_code': None, 'collector_number': None}
        
        # CORRECTED COORDINATES for MTG card set info
        # The set info is in the BOTTOM-LEFT corner:
        # - Vertical: last 5-7% of the card (93-100% of height)
        # - Horizontal: first 30-35% of the card (2-35% of width)
        
        # Primary region: focused on set info area
        set_top = int(h * 0.93)
        set_bottom = h
        set_left = int(w * 0.02)
        set_right = int(w * 0.35)
        
        bottom_strip = image[set_top:set_bottom, set_left:set_right]
        logger.debug(f"Set info: scanning bottom-left corner | y={set_top}-{set_bottom}, x={set_left}-{set_right} | size={bottom_strip.shape[1]}x{bottom_strip.shape[0]}")
        cv2.imwrite(os.path.join(debug_dir, 'set_info_strip.png'), bottom_strip)
        
        # Secondary region: slightly larger area for fallback
        region_top = int(h * 0.90)
        region_right = int(w * 0.40)
        bottom_region = image[region_top:set_bottom, set_left:region_right]
        cv2.imwrite(os.path.join(debug_dir, 'set_info_region.png'), bottom_region)
        
        # Try both regions
        regions_to_try = [
            ('strip', bottom_strip),
            ('region', bottom_region),
        ]
        
        for region_name, region in regions_to_try:
            if region.shape[0] < 10 or region.shape[1] < 10:
                continue
                
            # Convert to grayscale
            gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
            
            # Apply threshold to handle both light and dark text
            _, thresh_light = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
            _, thresh_dark = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
            
            # Also try adaptive threshold
            adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                            cv2.THRESH_BINARY, 11, 2)
            
            images_to_try = [
                ('gray', gray),
                ('inverted', cv2.bitwise_not(gray)),
                ('thresh_light', thresh_light),
                ('thresh_dark', thresh_dark),
                ('adaptive', adaptive),
            ]
            
            for img_name, img in images_to_try:
                # Scale up for better OCR (small text needs enlargement)
                scale = 3.0
                scaled = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                
                # Try OCR with different configs
                for psm in [7, 6, 13]:  # 7=single line, 6=block, 13=raw line
                    try:
                        pil_img = Image.fromarray(scaled)
                        config = f'--oem 3 --psm {psm}'
                        text = pytesseract.image_to_string(pil_img, config=config)
                        text = text.strip().upper()
                        
                        if not text or len(text) < 3:
                            continue
                        
                        logger.debug(f"Set OCR ({region_name}, {img_name}, PSM {psm}): '{text}'")
                        
                        # Pattern 1: Look for "NUMBER SET" format like "168 WOE" or "0168 WOE"
                        # Require at least 2 digits to avoid false positives
                        combined_pattern = r'0?(\d{2,4})\s*[/·\-]?\s*([A-Z]{3})'
                        match = re.search(combined_pattern, text)
                        if match:
                            num = match.group(1).lstrip('0') or '0'
                            potential_set = match.group(2)
                            if potential_set in known_sets and 1 <= int(num) <= 999:
                                best_result['collector_number'] = num
                                best_result['set_code'] = potential_set.lower()
                                logger.info(f"Found combined pattern: {num} {potential_set}")
                                return best_result
                        
                        # Pattern 2: Look for set code like "WOE · EN" or "WOE - EN" or just "WOE"
                        for set_code in known_sets:
                            # Look for set code with word boundary or separator
                            set_pattern = rf'\b{set_code}\b|{set_code}\s*[·\-]'
                            if re.search(set_pattern, text):
                                if not best_result['set_code']:
                                    best_result['set_code'] = set_code.lower()
                                    logger.info(f"Found set code: {set_code}")
                        
                        # Pattern 3: Look for collector number patterns
                        # Require at least 2 digits to avoid false positives from single digits
                        num_patterns = [
                            r'[UCRMLS]\s*0?(\d{2,4})\b',     # U 167, C 234, R 089 (rarity + number)
                            r'\b0?(\d{2,4})\b',              # 167, 0167, 68 (2-4 digits)
                            r'(\d{2,4})\s*/\s*\d+',          # 167/264 format
                        ]
                        
                        for pattern in num_patterns:
                            match = re.search(pattern, text)
                            if match and not best_result['collector_number']:
                                num = match.group(1).lstrip('0') or '0'
                                if 1 <= int(num) <= 999:
                                    best_result['collector_number'] = num
                                    logger.info(f"Found collector number: {num}")
                                    break
                        
                        # If we found both, return immediately
                        if best_result['set_code'] and best_result['collector_number']:
                            logger.info(f"Set info found: set={best_result['set_code']}, number={best_result['collector_number']}")
                            return best_result
                            
                    except Exception as e:
                        logger.debug(f"OCR attempt failed ({region_name}, {img_name}, PSM {psm}): {e}")
                        continue
        
        logger.info(f"Set info extraction result: set={best_result.get('set_code')}, number={best_result.get('collector_number')}")
        return best_result
    
    def extract_set_info_from_original(self, original_image: np.ndarray) -> Dict[str, str]:
        """
        Extract set code and collector number from the ORIGINAL photo.
        
        This is a fallback when the cropped card doesn't include the set info border.
        The set info is typically found at 70-76% of the image height for portrait photos
        where the card occupies the center of the frame.
        
        Returns dict with 'set_code' and 'collector_number'.
        """
        if not TESSERACT_AVAILABLE:
            logger.warning("Tesseract not available for set info extraction from original")
            return {'set_code': None, 'collector_number': None}
        
        h, w = original_image.shape[:2]
        logger.debug(f"Extracting set info from original image: {w}x{h}")
        
        # Save debug image
        debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', 'debug')
        os.makedirs(debug_dir, exist_ok=True)
        
        # Known MTG set codes
        known_sets = {
            'FIN', 'MKM', 'WOE', 'LCI', 'MOM', 'ONE', 'BRO', 'DMU', 'SNC', 'NEO',
            'VOW', 'MID', 'AFR', 'STX', 'KHM', 'ZNR', 'IKO', 'THB', 'ELD', 'WAR',
            'RNA', 'GRN', 'DOM', 'RIX', 'XLN', 'HOU', 'AKH', 'AER', 'KLD', 'EMN',
            'SOI', 'OGW', 'BFZ', 'DTK', 'FRF', 'KTK', 'M21', 'M20', 'M19', 'M15',
            'DSK', 'BLB', 'OTJ', 'MKC', 'CLU', 'PIP', 'ACR', 'WHO', 'LTR', 'CMM',
            'WOT', '2X2', 'CLB', 'NCC', 'SLD', 'J22', 'UNF', 'DMC', 'MUL', 'BRC',
            'BOT', 'BRR', 'ONC', 'MOM', 'MAT', 'MUL', 'LCC', 'RVR', 'SPG', 'PIO',
            'FDN', 'DSC', 'MH3', 'MH2', 'MH1', '40K', 'REX', '30A',
            # Spider-Man and Marvel sets
            'SPM', 'PSPM', 'TSPM', 'OM1'
        }
        
        best_result = {'set_code': None, 'collector_number': None}
        
        # For portrait photos (phone camera), the card is centered
        # Set info appears at roughly 70-76% of image height, 15-45% width
        # We scan multiple vertical strips to find it
        
        y_ranges = [
            (0.70, 0.76),  # Primary - where we found BLB in the test
            (0.68, 0.74),  # Slightly higher
            (0.72, 0.78),  # Slightly lower
            (0.65, 0.72),  # Even higher (for closer shots)
            (0.75, 0.82),  # Even lower (for further shots)
        ]
        
        x_start = int(w * 0.12)  # Left side where set info appears
        x_end = int(w * 0.50)    # Don't go too far right
        
        for y_start_pct, y_end_pct in y_ranges:
            y1 = int(h * y_start_pct)
            y2 = int(h * y_end_pct)
            
            region = original_image[y1:y2, x_start:x_end]
            
            if region.shape[0] < 20 or region.shape[1] < 50:
                continue
            
            # Convert and preprocess
            gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
            inverted = cv2.bitwise_not(gray)
            
            # Scale up for better OCR
            scaled = cv2.resize(inverted, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            
            # Try OCR
            for psm in [6, 7]:
                try:
                    text = pytesseract.image_to_string(scaled, config=f'--oem 3 --psm {psm}')
                    text = text.strip().upper()
                    
                    if not text or len(text) < 3:
                        continue
                    
                    logger.debug(f"Original set OCR (y={y_start_pct:.0%}-{y_end_pct:.0%}, PSM {psm}): '{text[:60]}'")
                    
                    # Look for collector number pattern: R 0053, U 0167, etc.
                    # Only set if we haven't found one yet!
                    if not best_result['collector_number']:
                        num_match = re.search(r'[RCUMLS]\s*0?(\d{2,4})\b', text)
                        if num_match:
                            num = num_match.group(1).lstrip('0') or '0'
                            if 1 <= int(num) <= 999:
                                best_result['collector_number'] = num
                                logger.info(f"Found collector number from original: {num}")
                        
                        # Also try plain number pattern
                        if not best_result['collector_number']:
                            num_match = re.search(r'\b0?(\d{2,4})\b', text)
                            if num_match:
                                num = num_match.group(1).lstrip('0') or '0'
                                if 1 <= int(num) <= 999:
                                    best_result['collector_number'] = num
                                    logger.info(f"Found collector number from original (plain): {num}")
                                logger.info(f"Found collector number from original (plain): {num}")
                    
                    # Look for set code - only if we haven't found one yet
                    if not best_result['set_code']:
                        for set_code in known_sets:
                            if set_code in text:
                                best_result['set_code'] = set_code.lower()
                                logger.info(f"Found set code from original: {set_code}")
                                break
                    
                    # If we found both, save debug and return
                    if best_result['set_code'] and best_result['collector_number']:
                        cv2.imwrite(os.path.join(debug_dir, 'set_info_from_original.png'), region)
                        logger.info(f"Set info from original: set={best_result['set_code']}, number={best_result['collector_number']}")
                        return best_result
                        
                except Exception as e:
                    logger.debug(f"OCR failed for original region: {e}")
                    continue
        
        # Save debug if we found partial info
        if best_result['set_code'] or best_result['collector_number']:
            logger.info(f"Partial set info from original: set={best_result.get('set_code')}, number={best_result.get('collector_number')}")
        
        return best_result
    
    def extract_set_info_ocr(self, image_normal: np.ndarray, image_inverted: np.ndarray) -> Dict[str, str]:
        """
        Extract set code and collector number from the set info region.
        Tries both normal and inverted versions to handle light-on-dark text.
        
        Card format (2 lines):
        Line 1: "U 0167" or "R 123" (rarity + number)
        Line 2: "FIN · EN" or "SET - EN" (set code + language)
        
        Returns dict with 'set_code' and 'collector_number'.
        """
        if not TESSERACT_AVAILABLE:
            logger.warning("Tesseract not available for set info extraction")
            return {'set_code': None, 'collector_number': None}
        
        # PSM modes to try:
        # 6 = Assume a single uniform block of text (good for 2 lines)
        # 4 = Assume a single column of text of variable sizes
        psm_modes = [6, 4, 7]
        
        # Try both images
        images_to_try = [
            ('inverted', image_inverted),
            ('normal', image_normal)
        ]
        
        best_result = {'set_code': None, 'collector_number': None, 'raw_text': ''}
        
        for img_name, img in images_to_try:
            for psm in psm_modes:
                try:
                    pil_img = Image.fromarray(img)
                    
                    # Allow all alphanumeric + common separators
                    config = f'--oem 3 --psm {psm} -l eng -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789·.- '
                    text = pytesseract.image_to_string(pil_img, config=config)
                    text = text.strip()
                    
                    if text:
                        logger.info(f"Set info OCR ({img_name}, PSM {psm}): '{text}'")
                        
                        set_code = None
                        collector_number = None
                        
                        # Parse the text looking for patterns
                        lines = text.replace('\n', ' ').split()
                        full_text = ' '.join(lines).upper()
                        
                        # Pattern 1: Look for 3-letter set codes (FIN, MKM, etc.)
                        set_match = re.search(r'\b([A-Z]{3})\b', full_text)
                        if set_match:
                            potential_set = set_match.group(1)
                            # Exclude common false positives like language codes
                            if potential_set not in ['THE', 'AND', 'FOR']:
                                set_code = potential_set.lower()
                        
                        # Pattern 2: Look for collector number (0167, 167, etc.)
                        # Usually 3-4 digits, may have leading zero
                        num_match = re.search(r'\b0?(\d{2,4})\b', full_text)
                        if num_match:
                            collector_number = num_match.group(1).lstrip('0') or '0'
                        
                        # If we found both, return immediately
                        if set_code and collector_number:
                            logger.info(f"Set info parsed: set={set_code}, number={collector_number}")
                            return {
                                'set_code': set_code,
                                'collector_number': collector_number,
                                'raw_text': text
                            }
                        
                        # Keep best partial result
                        if (set_code or collector_number) and not best_result['set_code']:
                            best_result = {
                                'set_code': set_code,
                                'collector_number': collector_number,
                                'raw_text': text
                            }
                            
                except Exception as e:
                    logger.debug(f"OCR attempt failed ({img_name}, PSM {psm}): {e}")
                    continue
        
        logger.info(f"Set info OCR raw text: '{best_result.get('raw_text', '')}'")
        logger.info(f"Set info parsed: set={best_result.get('set_code')}, number={best_result.get('collector_number')}")
        return best_result
    
    def extract_text_ocr(self, image: np.ndarray) -> str:
        """Extract text from image using Tesseract OCR"""
        if not TESSERACT_AVAILABLE:
            logger.warning("Tesseract not available")
            return ""
        
        try:
            # Convert to PIL for pytesseract
            pil_img = Image.fromarray(image)
            
            # Use simpler config - let Tesseract do its thing
            # PSM 6 = block (works better for card names based on testing)
            # PSM 7 = single line
            configs = [
                r'--oem 3 --psm 6 -l eng',   # Block of text, English (best for card names)
                r'--oem 3 --psm 7 -l eng',   # Single line, English
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
    
    def search_card_by_name(self, card_name: str, use_fuzzy: bool = True) -> Optional[Dict]:
        """
        Search for a Magic: The Gathering card by name using Scryfall API.
        Now includes fuzzy matching to correct OCR errors before API search.
        
        Args:
            card_name: The card name from OCR (may contain errors)
            use_fuzzy: Whether to use fuzzy matching to correct errors
            
        Returns:
            Card data dict or None
        """
        if not card_name or len(card_name) < 2:
            return None
        
        logger.debug(f"Searching card by name: '{card_name}'")
        
        # Step 1: Try fuzzy matching first to correct OCR errors
        corrected_name = card_name
        fuzzy_confidence = 0.0
        
        if use_fuzzy and self.fuzzy_matcher:
            try:
                matched_name, confidence = self.fuzzy_matcher.search_with_confidence(card_name)
                if matched_name:
                    corrected_name = matched_name
                    fuzzy_confidence = confidence
                    if matched_name != card_name:
                        logger.info(f"Fuzzy correction: '{card_name}' -> '{matched_name}' (conf={confidence:.2f})")
            except Exception as e:
                logger.warning(f"Fuzzy matching failed: {e}")
        
        # Step 2: Search via Scryfall API with the (possibly corrected) name
        try:
            result = self.scryfall_api.search_card_by_name(corrected_name)
            
            if result:
                logger.info(f"Found card via API: {result.get('name')}")
                # Add fuzzy matching metadata
                result['_fuzzy_corrected'] = corrected_name != card_name
                result['_original_ocr'] = card_name
                result['_fuzzy_confidence'] = fuzzy_confidence
                return result
            
            # If corrected name didn't work and it was different, try original
            if corrected_name != card_name:
                logger.debug(f"Corrected name failed, trying original: '{card_name}'")
                result = self.scryfall_api.search_card_by_name(card_name)
                if result:
                    logger.info(f"Found card via API (original): {result.get('name')}")
                    return result
            
        except Exception as e:
            logger.error(f"API search error: {e}")
        
        return None
    
    def search_card_with_suggestions(self, card_name: str) -> Dict:
        """
        Search for a card and return suggestions if no exact match found.
        
        Returns:
            Dict with 'card' (if found) and 'suggestions' list
        """
        result = {'card': None, 'suggestions': [], 'corrected_name': None}
        
        if not card_name or len(card_name) < 2:
            return result
        
        # Try fuzzy matching
        if self.fuzzy_matcher:
            try:
                # Get the best match
                matched_name, confidence = self.fuzzy_matcher.search_with_confidence(card_name)
                if matched_name:
                    result['corrected_name'] = matched_name
                    
                    # Try API search with corrected name
                    card_data = self.scryfall_api.search_card_by_name(matched_name)
                    if card_data:
                        result['card'] = card_data
                        result['card']['_fuzzy_confidence'] = confidence
                        return result
                
                # Get multiple suggestions
                suggestions = self.fuzzy_matcher.get_suggestions(card_name, max_results=5)
                result['suggestions'] = [name for name, dist in suggestions]
                
            except Exception as e:
                logger.warning(f"Fuzzy search failed: {e}")
        
        # Fallback to direct API search
        if not result['card']:
            try:
                card_data = self.scryfall_api.search_card_by_name(card_name)
                if card_data:
                    result['card'] = card_data
            except Exception as e:
                logger.error(f"API search error: {e}")
        
        return result

    def recognize_from_photo(self, image_path: str) -> Dict:
        """
        Main recognition method for mobile photos.
        Uses OCR to extract card name, then searches via Scryfall API.
        """
        logger.info(f"Recognizing card from photo | path={image_path}")
        
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
                    logger.info(f"OCR extracted: '{extracted_name}'")
                    
                    # Step 1: Try fuzzy matching to correct OCR errors first
                    corrected_name = extracted_name
                    fuzzy_confidence = 0.0
                    fuzzy_corrected = False
                    
                    if self.fuzzy_matcher:
                        try:
                            matched_name, confidence = self.fuzzy_matcher.search_with_confidence(extracted_name)
                            if matched_name:
                                corrected_name = matched_name
                                fuzzy_confidence = confidence
                                fuzzy_corrected = (matched_name.lower() != extracted_name.lower())
                                if fuzzy_corrected:
                                    logger.info(f"Fuzzy correction: '{extracted_name}' -> '{matched_name}' (conf={confidence:.2f})")
                        except Exception as e:
                            logger.warning(f"Fuzzy matching error: {e}")
                    
                    # Step 2: Search by corrected name
                    card_data = self.search_card_by_name(corrected_name, use_fuzzy=False)
                    
                    if card_data:
                        # Calculate confidence based on fuzzy match quality
                        confidence = 0.85 if not fuzzy_corrected else max(0.70, fuzzy_confidence)
                        method = 'ocr_fuzzy' if fuzzy_corrected else 'ocr'
                        
                        return {
                            'success': True,
                            'card': card_data,
                            'confidence': confidence,
                            'method': method,
                            'extracted_name': extracted_name,
                            'corrected_name': corrected_name if fuzzy_corrected else None,
                            'message': f"Card recognized via OCR: {card_data.get('name')}"
                        }
                    
                    # Step 3: If no match, try with suggestions
                    if self.fuzzy_matcher:
                        suggestions = self.fuzzy_matcher.get_suggestions(extracted_name, max_results=5)
                        for suggested_name, edit_dist in suggestions:
                            if suggested_name != corrected_name:
                                card_data = self.scryfall_api.search_card_by_name(suggested_name)
                                if card_data:
                                    return {
                                        'success': True,
                                        'card': card_data,
                                        'confidence': max(0.60, 1.0 - edit_dist/len(extracted_name)),
                                        'method': 'ocr_suggestion',
                                        'extracted_name': extracted_name,
                                        'corrected_name': suggested_name,
                                        'message': f"Card recognized via suggestion: {card_data.get('name')}"
                                    }
                    
                    # Step 4: Try partial name matching (legacy fallback)
                    words = extracted_name.split()
                    if len(words) >= 1:
                        for i in range(len(words), 0, -1):
                            partial_name = ' '.join(words[:i])
                            if len(partial_name) >= 3:
                                card_data = self.search_card_by_name(partial_name)
                                if card_data:
                                    return {
                                        'success': True,
                                        'card': card_data,
                                        'confidence': 0.65,
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
    
    def find_matching_card(self, image_hash: str) -> Optional[Tuple[Card, float]]:
        """
        Find matching card in database using perceptual hash
        Returns (Card, confidence_score) or None
        """
        logger.debug(f"Searching for matching card | hash={image_hash[:16]}...")
        db = get_db()
        
        try:
            with PerformanceLogger("find_matching_card"):
                # Query MTG cards from database
                query = db.query(Card).filter(Card.tcg == 'mtg')
                
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
    
    def recognize_card(self, image_path: str) -> Dict:
        """
        Main recognition pipeline for Magic: The Gathering cards:
        1. Try OCR for set code + collector number (most accurate)
        2. Try OCR for card name + API search
        3. Hash matching against local database
        """
        logger.info(f"Starting card recognition | path={image_path}")
        extracted_name = None  # Track extracted name for error feedback
        set_info = None  # Track set info for better matching
        
        try:
            with PerformanceLogger("recognize_card"):
                # Preprocess image - now also returns original for set info extraction
                processed_img, pil_img, original_img = self.preprocess_image(image_path)
                
                # Save debug images
                debug_dir = os.path.join(os.path.dirname(image_path), 'debug')
                os.makedirs(debug_dir, exist_ok=True)
                
                debug_processed = os.path.join(debug_dir, 'processed_card.png')
                cv2.imwrite(debug_processed, processed_img)
                logger.info(f"Saved processed card: {debug_processed} | shape={processed_img.shape}")
                
                # Also save the original for debug
                debug_original = os.path.join(debug_dir, 'original_card.png')
                cv2.imwrite(debug_original, original_img)
                logger.info(f"Saved original card: {debug_original} | shape={original_img.shape}")
                
                # Method 1: Try OCR + API search
                if TESSERACT_AVAILABLE:
                    logger.info("OCR available - trying text recognition...")
                    
                    # ===== STEP 1: Extract SET CODE and COLLECTOR NUMBER =====
                    # NEW APPROACH: Scan bottom portion of image for known patterns
                    logger.info("=== STEP 1: Trying SET CODE + COLLECTOR NUMBER extraction ===")
                    try:
                        # First try from processed/cropped card image
                        set_info = self.extract_set_info_from_full_image(processed_img)
                        logger.info(f"Set info from processed: set_code={set_info.get('set_code')}, collector_number={set_info.get('collector_number')}")
                        
                        # If not found in processed image, try the ORIGINAL photo
                        # (the crop might have cut off the set info border)
                        if not (set_info.get('set_code') and set_info.get('collector_number')):
                            logger.info("Set info incomplete in processed image, trying original photo...")
                            set_info_original = self.extract_set_info_from_original(original_img)
                            
                            # Merge results - prefer original if it has more info
                            if set_info_original.get('set_code') and not set_info.get('set_code'):
                                set_info['set_code'] = set_info_original['set_code']
                            if set_info_original.get('collector_number') and not set_info.get('collector_number'):
                                set_info['collector_number'] = set_info_original['collector_number']
                            
                            logger.info(f"Set info after original scan: set_code={set_info.get('set_code')}, collector_number={set_info.get('collector_number')}")
                        
                        # If we have both set code and collector number, search directly!
                        if set_info.get('set_code') and set_info.get('collector_number'):
                            logger.info(f"Trying precise search: set={set_info['set_code']}, number={set_info['collector_number']}")
                            
                            # Use Scryfall API to get exact card
                            card_data = self.scryfall_api.get_card_by_set_and_number(
                                set_info['set_code'], 
                                set_info['collector_number']
                            )
                            
                            if card_data:
                                logger.info(f"EXACT MATCH via set+number: {card_data.get('name')}")
                                return {
                                    'success': True,
                                    'card': card_data,
                                    'confidence': 0.98,  # Very high confidence for exact match
                                    'method': 'set_number',
                                    'set_code': set_info['set_code'],
                                    'collector_number': set_info['collector_number'],
                                    'message': f"Card identified: {card_data.get('name')} ({set_info['set_code'].upper()} #{set_info['collector_number']})"
                                }
                            else:
                                logger.warning(f"Set+number search failed for set={set_info['set_code']}, number={set_info['collector_number']}, falling back to name OCR")
                        else:
                            logger.info(f"Set info incomplete (set={set_info.get('set_code')}, num={set_info.get('collector_number')}), trying name OCR...")
                    except Exception as e:
                        logger.warning(f"Set info extraction failed: {e}", exc_info=True)
                    
                    # ===== STEP 2: Extract CARD NAME =====
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
                    logger.info(f"OCR extracted text: '{extracted_name}'")
                    
                    if extracted_name and len(extracted_name) >= 3:
                        # If we have a set code but no number, search name within that set
                        if set_info and set_info.get('set_code'):
                            card_data = self.search_card_by_name(f"{extracted_name} set:{set_info['set_code']}")
                            if not card_data:
                                # Try without set filter
                                card_data = self.search_card_by_name(extracted_name)
                        else:
                            card_data = self.search_card_by_name(extracted_name)
                        
                        if card_data:
                            confidence = 0.85
                            method = 'ocr_api'
                            
                            # Boost confidence if set matches
                            if set_info and set_info.get('set_code'):
                                card_set = card_data.get('set_code', '').lower()
                                if card_set == set_info['set_code'].lower():
                                    confidence = 0.92
                                    method = 'ocr_set_verified'
                            
                            logger.info(f"Recognition via OCR successful: {card_data.get('name')} | confidence={confidence}")
                            return {
                                'success': True,
                                'card': card_data,
                                'confidence': confidence,
                                'method': method,
                                'extracted_name': extracted_name,
                                'set_info': set_info,
                                'message': f"Card recognized: {card_data.get('name')}"
                            }
                        else:
                            logger.info(f"OCR found text '{extracted_name}' but no matching card in API")
                else:
                    logger.warning("Tesseract OCR not available - skipping text recognition")
                
                # Method 2: Direct API search with fuzzy matching
                # Try searching API directly (Scryfall has good fuzzy matching)
                logger.debug("Trying direct API search...")
                card_data = self.search_card_by_name_fuzzy(image_path)
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
                match = self.find_matching_card(img_hash)
                
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
                
                # No match found - include extracted_name if we got one
                logger.info(f"Recognition complete - no match found | extracted_name={extracted_name}")
                msg = 'No matching card found.'
                if extracted_name:
                    msg = f'Could not match "{extracted_name}". Try searching manually.'
                else:
                    msg = 'Could not read card name. Try better lighting or use Search by Name.'
                    
                return {
                    'success': False,
                    'card': None,
                    'confidence': 0.0,
                    'image_hash': img_hash if 'img_hash' in dir() else None,
                    'extracted_name': extracted_name,
                    'message': msg
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
    
    def search_card_by_name_fuzzy(self, image_path: str) -> Optional[Dict]:
        """
        Try to recognize card by sending image name hints to API.
        This is a placeholder for more advanced recognition.
        """
        # For now, return None - this would need a cloud vision API
        return None
    
    def batch_recognize(self, image_paths: List[str]) -> List[Dict]:
        """Recognize multiple cards in batch"""
        results = []
        for image_path in image_paths:
            result = self.recognize_card(image_path)
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
