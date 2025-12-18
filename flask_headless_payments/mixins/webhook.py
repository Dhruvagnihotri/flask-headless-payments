"""
flask_headless_payments.mixins.webhook
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Webhook event mixin for tracking Stripe webhooks.
"""


class WebhookEventMixin:
    """
    Mixin for WebhookEvent model.
    
    Tracks webhook events from Stripe for debugging and audit.
    """
    
    # Core fields
    id = None
    stripe_event_id = None
    event_type = None
    
    # Event data
    data = None  # JSON field
    
    # Processing
    processed = None
    processed_at = None
    error = None
    
    # Metadata
    received_at = None
    created_at = None
    
    def to_dict(self):
        """Convert webhook event to dictionary."""
        return {
            'id': self.id,
            'stripe_event_id': self.stripe_event_id,
            'event_type': self.event_type,
            'processed': self.processed,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
            'error': self.error,
            'received_at': self.received_at.isoformat() if self.received_at else None,
        }
    
    def __repr__(self):
        return f'<WebhookEvent {self.event_type} processed={self.processed}>'

