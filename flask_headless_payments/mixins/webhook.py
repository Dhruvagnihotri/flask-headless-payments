"""
flask_headless_payments.mixins.webhook
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Webhook event mixin for tracking Stripe webhooks.

Uses SQLAlchemy's declared_attr pattern so columns are automatically
created when the mixin is inherited.
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, JSON
from sqlalchemy.orm import declared_attr


class WebhookEventMixin:
    """
    Mixin for WebhookEvent model.
    
    Tracks webhook events from Stripe for debugging and audit.
    Columns are automatically created when you inherit this mixin.
    
    IMPORTANT: The column is named 'data' - if you override, keep this name
    as the webhook_manager expects it.
    """
    
    # Core fields - using declared_attr for proper column creation
    @declared_attr
    def stripe_event_id(cls):
        return Column(String(255), unique=True, nullable=False, index=True)
    
    @declared_attr
    def event_type(cls):
        return Column(String(100), nullable=False, index=True)
    
    # Event data - MUST be named 'data' for webhook_manager compatibility
    @declared_attr
    def data(cls):
        return Column(JSON, nullable=False)
    
    # Processing status
    @declared_attr
    def processed(cls):
        return Column(Boolean, default=False, nullable=False, index=True)
    
    @declared_attr
    def processed_at(cls):
        return Column(DateTime)
    
    @declared_attr
    def error(cls):
        return Column(Text)
    
    # Timestamps
    @declared_attr
    def received_at(cls):
        return Column(DateTime, default=datetime.utcnow, nullable=False)
    
    @declared_attr
    def created_at(cls):
        return Column(DateTime, default=datetime.utcnow, nullable=False)
    
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

