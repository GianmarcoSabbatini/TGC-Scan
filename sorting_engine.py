"""
TCG Scan - Sorting Engine
Implements all sorting algorithms for card organization
"""
from typing import List, Dict, Callable
from database import ScannedCard, Card, get_db
import config
from logger import get_logger

# Initialize logger for this module
logger = get_logger('sorting')

class SortingEngine:
    """Handles all card sorting logic"""
    
    def __init__(self):
        self.sorting_methods = {
            'alphabetic': self.sort_alphabetic,
            'set': self.sort_by_set,
            'color': self.sort_by_color,
            'type': self.sort_by_type,
            'rarity': self.sort_by_rarity,
            'price': self.sort_by_price
        }
        logger.info("SortingEngine initialized")
    
    def get_min_bins_for_criteria(self, criteria: str, tcg: str = 'mtg') -> int:
        """Get minimum number of bins required for a criteria"""
        if criteria == 'alphabetic':
            return 6  # A-D, E-H, I-L, M-P, Q-T, U-Z
        elif criteria == 'color':
            colors = config.SUPPORTED_TCGS.get(tcg, {}).get('colors', [])
            return len(colors) + 2  # colors + multicolor + colorless
        elif criteria == 'type':
            types = config.SUPPORTED_TCGS.get(tcg, {}).get('types', [])
            return len(types) + 1  # types + other
        elif criteria == 'rarity':
            rarities = config.SUPPORTED_TCGS.get(tcg, {}).get('rarities', [])
            return len(rarities) + 1  # rarities + unknown
        elif criteria == 'price':
            return len(config.PRICE_TIERS)  # 5 price tiers
        elif criteria == 'set':
            return 1  # Dynamic, no minimum
        else:
            return 6
    
    def sort_cards(self, cards: List[ScannedCard], criteria: str, 
                   sub_criteria: str = None, bin_count: int = 6) -> Dict[int, List[ScannedCard]]:
        """
        Sort cards into bins based on criteria
        Returns dict mapping bin_number -> list of cards
        """
        # Get TCG from first card for minimum calculation
        tcg = cards[0].card.tcg if cards and cards[0].card else 'mtg'
        
        # Get minimum bins for this criteria and enforce it
        min_bins = self.get_min_bins_for_criteria(criteria, tcg)
        if bin_count < min_bins:
            logger.info(f"bin_count {bin_count} too low for {criteria}, using minimum {min_bins}")
            bin_count = min_bins
        
        # Validate bin_count
        if bin_count < 1:
            bin_count = 6  # Default to 6 bins
            logger.warning(f"Invalid bin_count, defaulting to 6")
        
        logger.info(f"Sorting {len(cards)} cards | criteria={criteria} | sub={sub_criteria} | bins={bin_count}")
        
        if criteria not in self.sorting_methods:
            logger.error(f"Unknown sorting criteria: {criteria}")
            raise ValueError(f"Unknown sorting criteria: {criteria}")
        
        sorting_func = self.sorting_methods[criteria]
        result = sorting_func(cards, sub_criteria, bin_count)
        
        # Log distribution
        distribution = {k: len(v) for k, v in result.items()}
        logger.info(f"Sorting complete | distribution={distribution}")
        
        return result
    
    def sort_alphabetic(self, cards: List[ScannedCard], letter_position: str = '1st_letter', 
                       bin_count: int = 6) -> Dict[int, List[ScannedCard]]:
        """
        Sort cards alphabetically by 1st, 2nd, or 3rd letter
        Uses fixed letter ranges that match the bin labels (A-D, E-H, etc.)
        """
        # Determine which letter to use
        position_map = {
            '1st_letter': 0,
            '2nd_letter': 1,
            '3rd_letter': 2
        }
        letter_index = position_map.get(letter_position, 0)
        
        # Calculate letter ranges for each bin (same logic as get_bin_labels)
        letters_per_bin = 26 // bin_count
        
        def get_bin_for_letter(letter: str) -> int:
            """Get the bin number for a given letter based on fixed ranges"""
            if not letter or not letter.isalpha():
                return 1  # Non-alphabetic goes to first bin
            letter_ord = ord(letter.upper()) - 65  # A=0, B=1, etc.
            if letter_ord < 0 or letter_ord > 25:
                return 1
            # Calculate which bin this letter belongs to
            bin_num = (letter_ord // letters_per_bin) + 1
            # Make sure we don't exceed bin_count (last bin gets remaining letters)
            return min(bin_num, bin_count)
        
        bins = {i: [] for i in range(1, bin_count + 1)}
        
        for card in cards:
            name = card.card.name if card.card else ''
            if len(name) > letter_index:
                letter = name[letter_index].upper()
                bin_num = get_bin_for_letter(letter)
                bins[bin_num].append(card)
                card.bin_assignment = bin_num
                card.sorting_criteria = f'alphabetic_{letter_position}'
            else:
                # Card name too short, put in first bin
                bins[1].append(card)
                card.bin_assignment = 1
                card.sorting_criteria = f'alphabetic_{letter_position}'
        
        return bins
    
    def sort_by_set(self, cards: List[ScannedCard], sub_criteria: str = None, 
                    bin_count: int = 6) -> Dict[int, List[ScannedCard]]:
        """Sort cards by set/expansion"""
        # Group by set
        set_groups = {}
        for card in cards:
            set_code = card.card.set_code if card.card else 'unknown'
            if set_code not in set_groups:
                set_groups[set_code] = []
            set_groups[set_code].append(card)
        
        # Distribute sets across bins
        sorted_sets = sorted(set_groups.keys())
        bins = {i: [] for i in range(1, bin_count + 1)}
        
        for idx, set_code in enumerate(sorted_sets):
            bin_num = (idx % bin_count) + 1
            bins[bin_num].extend(set_groups[set_code])
        
        # Update bin assignments
        for bin_num, bin_cards in bins.items():
            for card in bin_cards:
                card.bin_assignment = bin_num
                card.sorting_criteria = 'set'
        
        return bins
    
    def sort_by_color(self, cards: List[ScannedCard], sub_criteria: str = None, 
                     bin_count: int = 6) -> Dict[int, List[ScannedCard]]:
        """Sort cards by color (MTG: WUBRG)"""
        # Get TCG from first card to determine color system
        tcg = cards[0].card.tcg if cards and cards[0].card else 'mtg'
        color_order = config.SUPPORTED_TCGS.get(tcg, {}).get('colors', [])
        
        # Build color to bin mapping (fixed positions)
        # Colors beyond bin_count go to last bin
        full_color_order = color_order + ['multicolor', 'colorless']
        color_to_bin = {}
        for idx, color in enumerate(full_color_order):
            bin_num = min(idx + 1, bin_count)
            color_to_bin[color] = bin_num
        
        bins = {i: [] for i in range(1, bin_count + 1)}
        
        for card in cards:
            colors = card.card.colors.split(',') if card.card and card.card.colors else []
            colors = [c.strip() for c in colors if c.strip()]
            
            if len(colors) == 0:
                bin_num = color_to_bin.get('colorless', bin_count)
            elif len(colors) == 1:
                color = colors[0]
                bin_num = color_to_bin.get(color, color_to_bin.get('multicolor', bin_count))
            else:
                bin_num = color_to_bin.get('multicolor', bin_count)
            
            bins[bin_num].append(card)
            card.bin_assignment = bin_num
            card.sorting_criteria = 'color'
        
        return bins
    
    def sort_by_type(self, cards: List[ScannedCard], sub_criteria: str = None, 
                    bin_count: int = 6) -> Dict[int, List[ScannedCard]]:
        """Sort cards by card type"""
        # Get TCG to determine types
        tcg = cards[0].card.tcg if cards and cards[0].card else 'mtg'
        type_order = config.SUPPORTED_TCGS.get(tcg, {}).get('types', [])
        
        # Build type to bin mapping (fixed positions)
        full_type_order = type_order + ['other']
        type_to_bin = {}
        for idx, card_type in enumerate(full_type_order):
            bin_num = min(idx + 1, bin_count)
            type_to_bin[card_type] = bin_num
        
        bins = {i: [] for i in range(1, bin_count + 1)}
        
        for card in cards:
            card_type_str = card.card.card_type if card.card else ''
            
            # Find matching type and get its fixed bin
            matched_type = 'other'
            for known_type in type_order:
                if known_type.lower() in card_type_str.lower():
                    matched_type = known_type
                    break
            
            bin_num = type_to_bin.get(matched_type, bin_count)
            bins[bin_num].append(card)
            card.bin_assignment = bin_num
            card.sorting_criteria = 'type'
        
        return bins
    
    def sort_by_rarity(self, cards: List[ScannedCard], sub_criteria: str = None, 
                      bin_count: int = 6) -> Dict[int, List[ScannedCard]]:
        """Sort cards by rarity"""
        # Get TCG to determine rarities
        tcg = cards[0].card.tcg if cards and cards[0].card else 'mtg'
        rarity_order = config.SUPPORTED_TCGS.get(tcg, {}).get('rarities', [])
        
        # Build rarity to bin mapping (fixed positions)
        # Rarities: common=1, uncommon=2, rare=3, mythic=4, unknown=last
        full_rarity_order = rarity_order + ['unknown']
        rarity_to_bin = {}
        for idx, rarity in enumerate(full_rarity_order):
            bin_num = min(idx + 1, bin_count)
            rarity_to_bin[rarity] = bin_num
        
        bins = {i: [] for i in range(1, bin_count + 1)}
        
        for card in cards:
            rarity = card.card.rarity if card.card else ''
            
            # Get the fixed bin for this rarity
            bin_num = rarity_to_bin.get(rarity, rarity_to_bin.get('unknown', bin_count))
            
            bins[bin_num].append(card)
            card.bin_assignment = bin_num
            card.sorting_criteria = 'rarity'
        
        return bins
    
    def sort_by_price(self, cards: List[ScannedCard], sub_criteria: str = None, 
                     bin_count: int = 5) -> Dict[int, List[ScannedCard]]:
        """Sort cards by price tier"""
        from api_integrations import CardAPIManager
        
        api_manager = CardAPIManager()
        
        # Assign cards to price tiers
        bins = {i: [] for i in range(1, min(bin_count, len(config.PRICE_TIERS)) + 1)}
        
        for card in cards:
            if not card.card:
                bins[1].append(card)  # Unknown cards go to bulk
                continue
            
            # Get latest price from price history or fetch from API
            price = None
            if card.card.price_history:
                latest_price = sorted(card.card.price_history, 
                                    key=lambda p: p.recorded_at, 
                                    reverse=True)[0]
                price = latest_price.price
            
            if price is None:
                price = 0.0  # Default to bulk
            
            # Find appropriate tier
            bin_num = 1
            for idx, tier in enumerate(config.PRICE_TIERS[:bin_count], start=1):
                if tier['min'] <= price < tier['max']:
                    bin_num = idx
                    break
            
            bins[bin_num].append(card)
            card.bin_assignment = bin_num
            card.sorting_criteria = 'price'
        
        return bins
    
    def get_bin_labels(self, criteria: str, bin_count: int, tcg: str = 'mtg') -> Dict[int, str]:
        """Get human-readable labels for bins based on sorting criteria"""
        if criteria == 'alphabetic':
            # A-D, E-H, I-L, M-P, Q-T, U-Z
            letters_per_bin = 26 // bin_count
            labels = {}
            for i in range(bin_count):
                start = chr(65 + i * letters_per_bin)
                end = chr(65 + (i + 1) * letters_per_bin - 1) if i < bin_count - 1 else 'Z'
                labels[i + 1] = f"{start}-{end}"
            return labels
        
        elif criteria == 'color':
            colors = config.SUPPORTED_TCGS.get(tcg, {}).get('colors', [])
            full_colors = colors + ['multicolor', 'colorless']
            labels = {}
            for i in range(bin_count):
                if i < len(full_colors):
                    labels[i + 1] = full_colors[i]
                else:
                    labels[i + 1] = f"Bin {i + 1}"
            return labels
        
        elif criteria == 'type':
            types = config.SUPPORTED_TCGS.get(tcg, {}).get('types', [])
            full_types = types + ['other']
            labels = {}
            for i in range(bin_count):
                if i < len(full_types):
                    labels[i + 1] = full_types[i]
                else:
                    labels[i + 1] = f"Bin {i + 1}"
            return labels
        
        elif criteria == 'rarity':
            rarities = config.SUPPORTED_TCGS.get(tcg, {}).get('rarities', [])
            full_rarities = rarities + ['unknown']
            labels = {}
            for i in range(bin_count):
                if i < len(full_rarities):
                    labels[i + 1] = full_rarities[i]
                else:
                    labels[i + 1] = f"Bin {i + 1}"
            return labels
        
        elif criteria == 'price':
            return {i + 1: tier['name'] for i, tier in enumerate(config.PRICE_TIERS[:bin_count])}
        
        elif criteria == 'set':
            return {i + 1: f"Set Group {i + 1}" for i in range(bin_count)}
        
        else:
            return {i: f"Bin {i}" for i in range(1, bin_count + 1)}
