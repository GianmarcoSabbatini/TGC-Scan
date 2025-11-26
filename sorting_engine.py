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
    
    def sort_cards(self, cards: List[ScannedCard], criteria: str, 
                   sub_criteria: str = None, bin_count: int = 6) -> Dict[int, List[ScannedCard]]:
        """
        Sort cards into bins based on criteria
        Returns dict mapping bin_number -> list of cards
        """
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
        """
        # Determine which letter to use
        position_map = {
            '1st_letter': 0,
            '2nd_letter': 1,
            '3rd_letter': 2
        }
        letter_index = position_map.get(letter_position, 0)
        
        # Group cards by letter
        letter_groups = {}
        for card in cards:
            name = card.card.name if card.card else ''
            if len(name) > letter_index:
                letter = name[letter_index].upper()
                if letter not in letter_groups:
                    letter_groups[letter] = []
                letter_groups[letter].append(card)
        
        # Distribute letters across bins
        sorted_letters = sorted(letter_groups.keys())
        letters_per_bin = max(1, len(sorted_letters) // bin_count)
        
        bins = {i: [] for i in range(1, bin_count + 1)}
        current_bin = 1
        letters_in_bin = 0
        
        for letter in sorted_letters:
            bins[current_bin].extend(letter_groups[letter])
            letters_in_bin += 1
            
            if letters_in_bin >= letters_per_bin and current_bin < bin_count:
                current_bin += 1
                letters_in_bin = 0
        
        # Update bin assignments
        for bin_num, bin_cards in bins.items():
            for card in bin_cards:
                card.bin_assignment = bin_num
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
        """Sort cards by color (MTG: WUBRG, Pokemon: types, etc.)"""
        # Get TCG from first card to determine color system
        tcg = cards[0].card.tcg if cards and cards[0].card else 'mtg'
        color_order = config.SUPPORTED_TCGS.get(tcg, {}).get('colors', [])
        
        # Group by color
        color_groups = {color: [] for color in color_order}
        color_groups['multicolor'] = []
        color_groups['colorless'] = []
        
        for card in cards:
            colors = card.card.colors.split(',') if card.card and card.card.colors else []
            colors = [c.strip() for c in colors if c.strip()]
            
            if len(colors) == 0:
                color_groups['colorless'].append(card)
            elif len(colors) == 1:
                color = colors[0]
                if color in color_groups:
                    color_groups[color].append(card)
                else:
                    color_groups['multicolor'].append(card)
            else:
                color_groups['multicolor'].append(card)
        
        # Assign bins (one bin per color if possible)
        bins = {i: [] for i in range(1, bin_count + 1)}
        bin_num = 1
        
        for color in color_order + ['multicolor', 'colorless']:
            if color in color_groups and color_groups[color]:
                bins[bin_num].extend(color_groups[color])
                bin_num = min(bin_num + 1, bin_count)
        
        # Update bin assignments
        for bin_num, bin_cards in bins.items():
            for card in bin_cards:
                card.bin_assignment = bin_num
                card.sorting_criteria = 'color'
        
        return bins
    
    def sort_by_type(self, cards: List[ScannedCard], sub_criteria: str = None, 
                    bin_count: int = 6) -> Dict[int, List[ScannedCard]]:
        """Sort cards by card type"""
        # Get TCG to determine types
        tcg = cards[0].card.tcg if cards and cards[0].card else 'mtg'
        type_order = config.SUPPORTED_TCGS.get(tcg, {}).get('types', [])
        
        # Group by type
        type_groups = {card_type: [] for card_type in type_order}
        type_groups['other'] = []
        
        for card in cards:
            card_type = card.card.card_type if card.card else ''
            
            # Find matching type
            matched = False
            for known_type in type_order:
                if known_type.lower() in card_type.lower():
                    type_groups[known_type].append(card)
                    matched = True
                    break
            
            if not matched:
                type_groups['other'].append(card)
        
        # Assign bins
        bins = {i: [] for i in range(1, bin_count + 1)}
        bin_num = 1
        
        for card_type in type_order + ['other']:
            if card_type in type_groups and type_groups[card_type]:
                bins[bin_num].extend(type_groups[card_type])
                bin_num = min(bin_num + 1, bin_count)
        
        # Update bin assignments
        for bin_num, bin_cards in bins.items():
            for card in bin_cards:
                card.bin_assignment = bin_num
                card.sorting_criteria = 'type'
        
        return bins
    
    def sort_by_rarity(self, cards: List[ScannedCard], sub_criteria: str = None, 
                      bin_count: int = 6) -> Dict[int, List[ScannedCard]]:
        """Sort cards by rarity"""
        # Get TCG to determine rarities
        tcg = cards[0].card.tcg if cards and cards[0].card else 'mtg'
        rarity_order = config.SUPPORTED_TCGS.get(tcg, {}).get('rarities', [])
        
        # Group by rarity
        rarity_groups = {rarity: [] for rarity in rarity_order}
        rarity_groups['unknown'] = []
        
        for card in cards:
            rarity = card.card.rarity if card.card else ''
            
            if rarity in rarity_groups:
                rarity_groups[rarity].append(card)
            else:
                rarity_groups['unknown'].append(card)
        
        # Assign bins (typically one bin per rarity)
        bins = {i: [] for i in range(1, bin_count + 1)}
        bin_num = 1
        
        for rarity in rarity_order + ['unknown']:
            if rarity in rarity_groups and rarity_groups[rarity]:
                bins[bin_num].extend(rarity_groups[rarity])
                bin_num = min(bin_num + 1, bin_count)
        
        # Update bin assignments
        for bin_num, bin_cards in bins.items():
            for card in bin_cards:
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
            return {i + 1: color for i, color in enumerate(colors[:bin_count])}
        
        elif criteria == 'rarity':
            rarities = config.SUPPORTED_TCGS.get(tcg, {}).get('rarities', [])
            return {i + 1: rarity for i, rarity in enumerate(rarities[:bin_count])}
        
        elif criteria == 'price':
            return {i + 1: tier['name'] for i, tier in enumerate(config.PRICE_TIERS[:bin_count])}
        
        else:
            return {i: f"Bin {i}" for i in range(1, bin_count + 1)}
