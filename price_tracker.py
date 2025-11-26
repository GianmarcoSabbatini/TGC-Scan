"""
TCG Scan - Price Tracking Module
Handles real-time price tracking and historical data
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from database import Card, PriceHistory, get_db
from api_integrations import CardAPIManager
import config
from logger import get_logger

# Initialize logger for this module
logger = get_logger('price')

class PriceTracker:
    """Manages price tracking and updates"""
    
    def __init__(self):
        self.api_manager = CardAPIManager()
        logger.info("PriceTracker initialized")
        
    def update_card_price(self, card: Card) -> Optional[float]:
        """
        Update price for a single card
        Returns the new price or None if update failed
        """
        logger.debug(f"Updating price for card | id={card.id} | name={card.name} | tcg={card.tcg}")
        db = get_db()
        
        try:
            # Fetch current price from API
            if card.tcg == 'mtg':
                card_data = self.api_manager.scryfall.get_card_by_set_and_number(
                    card.set_code, card.collector_number
                )
            elif card.tcg == 'pokemon':
                card_data = self.api_manager.pokemon.search_card_by_name(card.name)
            elif card.tcg == 'yugioh':
                card_data = self.api_manager.yugioh.search_card_by_name(card.name)
            else:
                logger.warning(f"Unknown TCG for price update: {card.tcg}")
                return None
            
            if not card_data:
                logger.debug(f"No API data found for card: {card.name}")
                return None
            
            # Extract price
            price = self.api_manager.get_card_price(card_data)
            
            if price is not None:
                # Save to price history
                price_record = PriceHistory(
                    card_id=card.id,
                    price=price,
                    price_source='api',
                    currency='USD'
                )
                db.add(price_record)
                db.commit()
                
                logger.info(f"Price updated | card={card.name} | price=${price:.2f}")
                return price
            
            return None
            
        except Exception as e:
            logger.error(f"Error updating price for {card.name}: {e}", exc_info=True)
            db.rollback()
            return None
        finally:
            db.close()
    
    def update_all_prices(self, tcg: str = None, max_cards: int = None) -> Dict[str, int]:
        """
        Update prices for all cards (or filtered by TCG)
        Returns statistics about the update
        """
        logger.info(f"Starting bulk price update | tcg={tcg} | max_cards={max_cards}")
        db = get_db()
        
        try:
            query = db.query(Card)
            if tcg:
                query = query.filter(Card.tcg == tcg)
            
            if max_cards:
                cards = query.limit(max_cards).all()
            else:
                cards = query.all()
            
            stats = {
                'total': len(cards),
                'updated': 0,
                'failed': 0,
                'skipped': 0
            }
            
            logger.info(f"Processing {stats['total']} cards for price update")
            
            for card in cards:
                # Check if we need to update (based on last update time)
                if self._should_update_price(card):
                    price = self.update_card_price(card)
                    if price is not None:
                        stats['updated'] += 1
                    else:
                        stats['failed'] += 1
                else:
                    stats['skipped'] += 1
            
            logger.info(f"Bulk price update complete | stats={stats}")
            return stats
            
        finally:
            db.close()
    
    def _should_update_price(self, card: Card) -> bool:
        """Check if card price should be updated based on last update time"""
        if not card.price_history:
            return True
        
        latest_price = sorted(card.price_history, 
                            key=lambda p: p.recorded_at, 
                            reverse=True)[0]
        
        time_since_update = datetime.utcnow() - latest_price.recorded_at
        update_interval = timedelta(seconds=config.PRICE_UPDATE_INTERVAL)
        
        return time_since_update >= update_interval
    
    def get_card_price_history(self, card_id: int, days: int = 30) -> List[Dict]:
        """Get price history for a card over the last N days"""
        db = get_db()
        
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            prices = db.query(PriceHistory).filter(
                PriceHistory.card_id == card_id,
                PriceHistory.recorded_at >= cutoff_date
            ).order_by(PriceHistory.recorded_at).all()
            
            return [p.to_dict() for p in prices]
            
        finally:
            db.close()
    
    def get_current_price(self, card_id: int) -> Optional[float]:
        """Get the most recent price for a card"""
        db = get_db()
        
        try:
            latest_price = db.query(PriceHistory).filter(
                PriceHistory.card_id == card_id
            ).order_by(PriceHistory.recorded_at.desc()).first()
            
            return latest_price.price if latest_price else None
            
        finally:
            db.close()
    
    def get_price_tier(self, price: float) -> Optional[str]:
        """Determine price tier for a given price"""
        if price is None:
            return None
        for tier in config.PRICE_TIERS:
            if tier['min'] <= price < tier['max']:
                return tier['name']
        return 'Unknown'
    
    def get_collection_value(self, collection_id: int = None) -> Dict:
        """
        Calculate total value of a collection
        Returns dict with total value and breakdown by tier
        """
        db = get_db()
        
        try:
            from database import ScannedCard, Card
            from sqlalchemy.orm import joinedload
            
            query = db.query(ScannedCard).options(joinedload(ScannedCard.card))
            if collection_id:
                query = query.filter(ScannedCard.collection_id == collection_id)
            
            scanned_cards = query.all()
            
            total_value = 0.0
            tier_breakdown = {tier['name']: {'count': 0, 'value': 0.0} 
                            for tier in config.PRICE_TIERS}
            
            for scanned_card in scanned_cards:
                if not scanned_card.card:
                    continue
                
                price = self.get_current_price(scanned_card.card.id)
                if price is not None:
                    card_value = price * scanned_card.quantity
                    total_value += card_value
                    
                    tier = self.get_price_tier(price)
                    if tier and tier in tier_breakdown:
                        tier_breakdown[tier]['count'] += scanned_card.quantity
                        tier_breakdown[tier]['value'] += card_value
            
            return {
                'total_value': round(total_value, 2),
                'currency': 'USD',
                'tier_breakdown': tier_breakdown,
                'card_count': len(scanned_cards)
            }
            
        finally:
            db.close()
