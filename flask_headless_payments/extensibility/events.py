"""
flask_headless_payments.extensibility.events
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Event system for reactive extensions.
"""

import logging
from typing import Callable, Dict, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class Event:
    """
    Represents an event that occurred.
    
    Attributes:
        name: Event name
        data: Event data
        timestamp: When event occurred
        source: Event source
    """
    
    def __init__(self, name: str, data: Dict[str, Any], source: str = None):
        self.name = name
        self.data = data
        self.timestamp = datetime.utcnow()
        self.source = source or 'flask-headless-payments'
    
    def to_dict(self):
        return {
            'name': self.name,
            'data': self.data,
            'timestamp': self.timestamp.isoformat(),
            'source': self.source
        }


class EventManager:
    """
    Event-driven extension system.
    
    Unlike hooks (which modify behavior), events notify observers.
    
    Example:
        @event_manager.subscribe('subscription.created')
        def send_welcome_email(event):
            user_id = event.data['user_id']
            send_email(user_id, 'Welcome!')
    """
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._event_history: List[Event] = []
        self._max_history = 1000
    
    def subscribe(self, event_name: str):
        """
        Subscribe to an event.
        
        Args:
            event_name: Event name to subscribe to
        
        Usage:
            @event_manager.subscribe('subscription.created')
            def on_subscription_created(event):
                print(f"New subscription: {event.data['subscription_id']}")
        """
        def decorator(func: Callable):
            if event_name not in self._subscribers:
                self._subscribers[event_name] = []
            
            self._subscribers[event_name].append(func)
            logger.info(f"Subscribed to event '{event_name}': {func.__name__}")
            return func
        
        return decorator
    
    def publish(self, event_name: str, data: Dict[str, Any], source: str = None):
        """
        Publish an event to all subscribers.
        
        Args:
            event_name: Name of the event
            data: Event data
            source: Event source (optional)
        """
        event = Event(event_name, data, source)
        
        # Store in history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)
        
        # Notify subscribers
        if event_name in self._subscribers:
            for subscriber in self._subscribers[event_name]:
                try:
                    subscriber(event)
                except Exception as e:
                    logger.error(f"Error in event subscriber '{event_name}': {e}")
    
    def get_history(self, event_name: str = None, limit: int = 100) -> List[Event]:
        """
        Get event history.
        
        Args:
            event_name: Filter by event name (optional)
            limit: Maximum events to return
        
        Returns:
            list: Recent events
        """
        events = self._event_history
        
        if event_name:
            events = [e for e in events if e.name == event_name]
        
        return events[-limit:]


# Global event manager
_event_manager = EventManager()


def event(event_name: str):
    """
    Decorator to subscribe to an event.
    
    Usage:
        from flask_headless_payments.extensibility import event
        
        @event('subscription.created')
        def on_new_subscription(evt):
            print(f"User {evt.data['user_id']} subscribed!")
    """
    return _event_manager.subscribe(event_name)


def get_event_manager() -> EventManager:
    """Get global event manager."""
    return _event_manager


# Available events documentation
AVAILABLE_EVENTS = {
    # Customer events
    'customer.created': 'Stripe customer created',
    'customer.updated': 'Customer information updated',
    
    # Subscription events
    'subscription.created': 'New subscription created',
    'subscription.updated': 'Subscription modified',
    'subscription.cancelled': 'Subscription cancelled',
    'subscription.renewed': 'Subscription renewed',
    'subscription.expired': 'Subscription expired',
    
    # Payment events
    'payment.succeeded': 'Payment successful',
    'payment.failed': 'Payment failed',
    'payment.refunded': 'Payment refunded',
    
    # Webhook events
    'webhook.received': 'Webhook received from Stripe',
    'webhook.processed': 'Webhook processed successfully',
    'webhook.failed': 'Webhook processing failed',
    
    # Plan events
    'plan.upgraded': 'User upgraded plan',
    'plan.downgraded': 'User downgraded plan',
    
    # Error events
    'error.stripe_api': 'Stripe API error occurred',
    'error.database': 'Database error occurred',
}

