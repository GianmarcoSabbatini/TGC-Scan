"""
TCG Scan - Price Tracking Module
Handles real-time price tracking and historical data
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
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
        Update price for a single MTG card
        Returns the new price or None if update failed
        """
        logger.debug(f"Updating price for card | id={card.id} | name={card.name}")
        db = get_db()
        
        try:
            # Fetch current price from Scryfall API
            card_data = self.api_manager.scryfall.get_card_by_set_and_number(
                card.set_code, card.collector_number
            )
            
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
                
                # Use DEBUG level to avoid spamming console
                logger.debug(f"Price updated | card={card.name} | price=${price:.2f}")
                return price
            
            return None
            
        except Exception as e:
            logger.error(f"Error updating price for {card.name}: {e}", exc_info=True)
            db.rollback()
            return None
        finally:
            db.close()
    
    def update_all_prices(self, max_cards: int = None) -> Dict[str, int]:
        """
        Update prices for all MTG cards
        Returns statistics about the update
        """
        logger.info(f"Starting bulk price update | max_cards={max_cards}")
        db = get_db()
        
        try:
            query = db.query(Card).filter(Card.tcg == 'mtg')
            
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
    
    def get_current_price(self, card_id: int, currency: str = 'EUR') -> Optional[float]:
        """Get the most recent price for a card (prefers EUR)"""
        db = get_db()
        
        try:
            # First try to get price in preferred currency
            latest_price = db.query(PriceHistory).filter(
                PriceHistory.card_id == card_id,
                PriceHistory.currency == currency
            ).order_by(PriceHistory.recorded_at.desc()).first()
            
            # Fallback to any currency if preferred not found
            if not latest_price:
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
                'currency': 'EUR',
                'tier_breakdown': tier_breakdown,
                'card_count': len(scanned_cards)
            }
            
        finally:
            db.close()
    
    def get_price_trend(self, card_id: int, days: int = 7) -> Dict:
        """
        Calculate price trend for a card over the last N days
        Returns trend direction, percentage change, and price data
        """
        db = get_db()
        
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Get all prices in the period, ordered by date
            prices = db.query(PriceHistory).filter(
                PriceHistory.card_id == card_id,
                PriceHistory.recorded_at >= cutoff_date
            ).order_by(PriceHistory.recorded_at.asc()).all()
            
            if len(prices) < 2:
                # Not enough data for trend
                current = prices[-1].price if prices else None
                return {
                    'trend': 'stable',
                    'trend_icon': '→',
                    'current_price': current,
                    'previous_price': None,
                    'change_amount': 0,
                    'change_percent': 0,
                    'data_points': len(prices)
                }
            
            # Get oldest and newest price in the period
            oldest_price = prices[0].price
            newest_price = prices[-1].price
            
            # Calculate change
            change_amount = newest_price - oldest_price
            change_percent = (change_amount / oldest_price * 100) if oldest_price > 0 else 0
            
            # Determine trend (threshold of 2% to avoid noise)
            if change_percent > 2:
                trend = 'up'
                trend_icon = '↑'
            elif change_percent < -2:
                trend = 'down'
                trend_icon = '↓'
            else:
                trend = 'stable'
                trend_icon = '→'
            
            return {
                'trend': trend,
                'trend_icon': trend_icon,
                'current_price': round(newest_price, 2),
                'previous_price': round(oldest_price, 2),
                'change_amount': round(change_amount, 2),
                'change_percent': round(change_percent, 1),
                'data_points': len(prices)
            }
            
        finally:
            db.close()
    
    def get_price_with_trend(self, card_id: int) -> Dict:
        """Get current price along with trend information"""
        current_price = self.get_current_price(card_id)
        trend_data = self.get_price_trend(card_id)
        
        return {
            'price': current_price,
            'currency': 'EUR',
            **trend_data
        }
