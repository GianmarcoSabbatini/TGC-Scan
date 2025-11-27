"""
TCG Scan - Fuzzy Card Name Matcher
Uses SymSpell for fast fuzzy matching to correct OCR errors.
Based on techniques from mtgscan project.
"""
import json
import re
import os
from pathlib import Path
from typing import Optional, Tuple, List, Set
import requests

from symspellpy import SymSpell, Verbosity, editdistance

from logger import get_logger

logger = get_logger('fuzzy_matcher')

# URLs for downloading card data
URL_ALL_CARDS = "https://mtgjson.com/api/v5/AtomicCards.json"
URL_KEYWORDS = "https://mtgjson.com/api/v5/Keywords.json"

# Default paths for dictionary files
DATA_DIR = Path(__file__).parent / "data"
FILE_ALL_CARDS = DATA_DIR / "all_cards.txt"
FILE_KEYWORDS = DATA_DIR / "keywords.json"


class FuzzyCardMatcher:
    """
    Fuzzy matcher for Magic card names using SymSpell.
    
    Key features:
    - Corrects OCR errors using edit distance
    - Handles truncated names (ending with ..)
    - Filters out common keywords that appear on cards
    - Fast lookup using SymSpell's symmetric delete algorithm
    """
    
    def __init__(
        self,
        file_all_cards: str = None,
        file_keywords: str = None,
        max_ratio_diff: float = 0.3,
        max_ratio_diff_keyword: float = 0.2,
        max_edit_distance: int = 6
    ):
        """
        Initialize the fuzzy matcher.
        
        Args:
            file_all_cards: Path to card dictionary file. Downloads if not exists.
            file_keywords: Path to keywords file. Downloads if not exists.
            max_ratio_diff: Maximum ratio (distance/length) to consider a match
            max_ratio_diff_keyword: Maximum ratio for keyword rejection
            max_edit_distance: Maximum edit distance for SymSpell
        """
        self.max_ratio_diff = max_ratio_diff
        self.max_ratio_diff_keyword = max_ratio_diff_keyword
        self.max_edit_distance = max_edit_distance
        
        # Use default paths if not provided
        if file_all_cards is None:
            file_all_cards = str(FILE_ALL_CARDS)
        if file_keywords is None:
            file_keywords = str(FILE_KEYWORDS)
        
        # Ensure data directory exists
        DATA_DIR.mkdir(exist_ok=True)
        
        # Load card dictionary
        self._load_card_dictionary(file_all_cards)
        
        # Load keywords dictionary
        self._load_keywords_dictionary(file_keywords)
        
        # Edit distance calculator for prefix matching
        self.edit_dist = editdistance.EditDistance(editdistance.DistanceAlgorithm.LEVENSHTEIN)
        
        logger.info(f"FuzzyCardMatcher initialized | cards={len(self.all_cards)} | keywords={len(self.keywords)}")
    
    def _download_json(self, url: str) -> dict:
        """Download JSON data from URL."""
        logger.info(f"Downloading: {url}")
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            raise
    
    def _load_card_dictionary(self, file_path: str):
        """Load or download the card dictionary."""
        path = Path(file_path)
        
        if not path.is_file():
            logger.info(f"Card dictionary not found, downloading from MTGJSON...")
            try:
                all_cards_json = self._download_json(URL_ALL_CARDS)
                
                # Extract card names and write to file
                with path.open("w", encoding="utf-8") as f:
                    for card_name, card_data in all_cards_json.get("data", {}).items():
                        # Clean up card name (remove // for split cards)
                        clean_name = card_name
                        if " // " in card_name:
                            clean_name = card_name.split(" // ")[0]
                        
                        # Write in SymSpell format: word$frequency
                        f.write(f"{clean_name}$1\n")
                
                logger.info(f"Card dictionary saved to {path}")
            except Exception as e:
                logger.error(f"Failed to create card dictionary: {e}")
                # Create empty dictionary as fallback
                path.touch()
        
        # Initialize SymSpell with card dictionary
        self.sym_all_cards = SymSpell(max_dictionary_edit_distance=self.max_edit_distance)
        self.sym_all_cards._distance_algorithm = editdistance.DistanceAlgorithm.LEVENSHTEIN
        
        if path.stat().st_size > 0:
            self.sym_all_cards.load_dictionary(str(path), term_index=0, count_index=1, separator="$")
            self.all_cards = self.sym_all_cards._words
            logger.info(f"Loaded card dictionary: {len(self.all_cards)} cards")
        else:
            self.all_cards = {}
            logger.warning("Card dictionary is empty")
    
    def _load_keywords_dictionary(self, file_path: str):
        """Load or download the keywords dictionary."""
        path = Path(file_path)
        
        if not path.is_file():
            logger.info(f"Keywords dictionary not found, downloading from MTGJSON...")
            try:
                keywords_json = self._download_json(URL_KEYWORDS)
                with path.open("w", encoding="utf-8") as f:
                    json.dump(keywords_json, f)
                logger.info(f"Keywords dictionary saved to {path}")
            except Exception as e:
                logger.error(f"Failed to download keywords: {e}")
                # Create empty keywords file
                with path.open("w") as f:
                    json.dump({"data": {}}, f)
        
        # Load keywords from JSON
        with path.open("r", encoding="utf-8") as f:
            keywords_json = json.load(f)
        
        # Extract all keywords from all categories
        self.keywords: Set[str] = set()
        for category, keyword_list in keywords_json.get("data", {}).items():
            if isinstance(keyword_list, list):
                self.keywords.update(keyword_list)
        
        # Add common UI/card text that should be ignored
        ui_keywords = [
            "Display", "Land", "Search", "Profile", "Deck", "Hand", "Library",
            "Graveyard", "Exile", "Battlefield", "Stack", "Command", "Creature",
            "Instant", "Sorcery", "Enchantment", "Artifact", "Planeswalker",
            "Legendary", "Basic", "Snow", "Token", "Copy", "Counter", "Target",
            "Player", "Opponent", "Controller", "Owner", "Card", "Spell", "Ability",
            "Mana", "Life", "Damage", "Combat", "Attack", "Block", "Tap", "Untap",
            "Draw", "Discard", "Sacrifice", "Destroy", "Return", "Put", "Remove",
            "Add", "Gain", "Lose", "Pay", "Cost", "Effect", "Trigger", "Activated",
            "Static", "Replacement", "Prevention", "Protection", "Hexproof",
            "Indestructible", "Deathtouch", "Lifelink", "First", "Strike", "Double",
            "Vigilance", "Reach", "Flying", "Trample", "Haste", "Flash", "Defender",
            "Menace", "Prowess", "Ward", "Toxic", "Corrupted", "Oil"
        ]
        self.keywords.update(ui_keywords)
        
        # Initialize SymSpell for keywords
        self.sym_keywords = SymSpell(max_dictionary_edit_distance=3)
        for keyword in self.keywords:
            self.sym_keywords.create_dictionary_entry(keyword, 1)
        
        logger.info(f"Loaded keywords dictionary: {len(self.keywords)} keywords")
    
    def preprocess_text(self, text: str) -> str:
        """
        Clean up OCR text by removing invalid characters.
        
        MTG card names only contain: letters, apostrophes, commas, periods, spaces, and hyphens.
        """
        if not text:
            return ""
        
        # Remove characters that can't appear on a Magic card name
        cleaned = re.sub(r"[^a-zA-Z',.\- ]", '', text)
        
        # Normalize whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    def is_keyword(self, text: str) -> bool:
        """
        Check if text is a keyword that should be ignored.
        
        Returns True if text matches a known keyword closely.
        """
        if not text or len(text) < 3:
            return False
        
        max_dist = min(3, int(self.max_ratio_diff_keyword * len(text)))
        suggestions = self.sym_keywords.lookup(
            text,
            Verbosity.CLOSEST,
            max_edit_distance=max_dist
        )
        
        if suggestions:
            ratio = suggestions[0].distance / len(text)
            if ratio <= self.max_ratio_diff_keyword:
                logger.debug(f"Keyword rejected: '{text}' -> '{suggestions[0].term}' (ratio={ratio:.2f})")
                return True
        
        return False
    
    def search(self, text: str) -> Optional[str]:
        """
        Search for a card name matching the input text.
        
        Uses fuzzy matching to handle OCR errors.
        
        Args:
            text: Raw OCR text to match
            
        Returns:
            Matched card name or None if no match found
        """
        if not text:
            return None
        
        # Preprocess
        text = self.preprocess_text(text)
        
        # Reject too short or too long
        if len(text) < 3:
            logger.debug(f"Too short: '{text}'")
            return None
        
        if len(text) > 50:
            logger.debug(f"Too long: '{text}'")
            return None
        
        # Reject if it's a keyword
        if self.is_keyword(text):
            return None
        
        # Check for exact match first
        if text in self.all_cards:
            logger.info(f"Exact match: '{text}'")
            return text
        
        # Check for truncated name (ends with ..)
        if ".." in text:
            return self._search_prefix(text)
        
        # Fuzzy search
        return self._search_fuzzy(text)
    
    def _search_prefix(self, text: str) -> Optional[str]:
        """Search for a card with truncated name."""
        idx = text.find("..")
        if idx < 3:
            return None
        
        prefix = text[:idx]
        max_dist = int(self.max_ratio_diff * idx)
        
        best_card = None
        best_dist = max_dist + 1
        
        for card in self.all_cards:
            if len(card) >= idx:
                dist = self.edit_dist.compare(prefix, card[:idx], max_dist)
                if dist != -1 and dist < best_dist:
                    best_card = card
                    best_dist = dist
        
        if best_card:
            logger.info(f"Prefix match: '{text}' -> '{best_card}' (dist={best_dist})")
            return best_card
        
        logger.debug(f"No prefix match: '{text}'")
        return None
    
    def _search_fuzzy(self, text: str) -> Optional[str]:
        """Perform fuzzy search for card name."""
        # Remove trailing periods and spaces
        text = text.replace('.', '').rstrip(' ')
        
        # Calculate max edit distance based on text length
        max_dist = min(self.max_edit_distance, int(self.max_ratio_diff * len(text)))
        
        suggestions = self.sym_all_cards.lookup(
            text,
            Verbosity.CLOSEST,
            max_edit_distance=max_dist
        )
        
        if suggestions:
            best = suggestions[0]
            ratio = best.distance / len(text)
            
            # Accept if the match is good and text isn't too much longer than card name
            if len(text) < len(best.term) + 7:
                logger.info(f"Fuzzy match: '{text}' -> '{best.term}' (dist={best.distance}, ratio={ratio:.2f})")
                return best.term
            else:
                logger.debug(f"Rejected (too long): '{text}' -> '{best.term}'")
        else:
            logger.debug(f"No fuzzy match: '{text}'")
        
        return None
    
    def search_with_confidence(self, text: str) -> Tuple[Optional[str], float]:
        """
        Search for a card name and return confidence score.
        
        Args:
            text: Raw OCR text to match
            
        Returns:
            Tuple of (matched_card_name, confidence_score)
            Confidence is 1.0 for exact match, decreases with edit distance
        """
        if not text:
            return None, 0.0
        
        # Preprocess
        text = self.preprocess_text(text)
        
        if len(text) < 3 or len(text) > 50:
            return None, 0.0
        
        if self.is_keyword(text):
            return None, 0.0
        
        # Exact match
        if text in self.all_cards:
            return text, 1.0
        
        # Handle truncated names
        if ".." in text:
            card = self._search_prefix(text)
            if card:
                idx = text.find("..")
                prefix = text[:idx]
                dist = self.edit_dist.compare(prefix, card[:idx], 10)
                confidence = max(0.5, 1.0 - (dist / len(prefix)) * 0.5)
                return card, confidence
            return None, 0.0
        
        # Fuzzy search
        text_clean = text.replace('.', '').rstrip(' ')
        max_dist = min(self.max_edit_distance, int(self.max_ratio_diff * len(text_clean)))
        
        suggestions = self.sym_all_cards.lookup(
            text_clean,
            Verbosity.CLOSEST,
            max_edit_distance=max_dist
        )
        
        if suggestions and len(text_clean) < len(suggestions[0].term) + 7:
            best = suggestions[0]
            # Confidence based on edit distance ratio
            confidence = max(0.3, 1.0 - (best.distance / len(text_clean)))
            return best.term, confidence
        
        return None, 0.0
    
    def get_suggestions(self, text: str, max_results: int = 5) -> List[Tuple[str, int]]:
        """
        Get multiple card name suggestions for the input text.
        
        Args:
            text: Raw OCR text
            max_results: Maximum number of suggestions
            
        Returns:
            List of (card_name, edit_distance) tuples
        """
        if not text:
            return []
        
        text = self.preprocess_text(text)
        
        if len(text) < 3:
            return []
        
        text_clean = text.replace('.', '').rstrip(' ')
        max_dist = min(self.max_edit_distance, int(self.max_ratio_diff * len(text_clean)))
        
        suggestions = self.sym_all_cards.lookup(
            text_clean,
            Verbosity.ALL,
            max_edit_distance=max_dist
        )
        
        return [(s.term, s.distance) for s in suggestions[:max_results]]


# Singleton instance for convenience
_matcher_instance: Optional[FuzzyCardMatcher] = None


def get_fuzzy_matcher() -> FuzzyCardMatcher:
    """Get or create the singleton FuzzyCardMatcher instance."""
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = FuzzyCardMatcher()
    return _matcher_instance


def fuzzy_search_card(text: str) -> Optional[str]:
    """
    Convenience function to search for a card name.
    
    Args:
        text: Raw OCR text
        
    Returns:
        Matched card name or None
    """
    return get_fuzzy_matcher().search(text)


def fuzzy_search_with_confidence(text: str) -> Tuple[Optional[str], float]:
    """
    Convenience function to search with confidence score.
    
    Args:
        text: Raw OCR text
        
    Returns:
        Tuple of (card_name, confidence)
    """
    return get_fuzzy_matcher().search_with_confidence(text)
