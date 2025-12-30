"""
flask_headless_payments.mixins.payment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Payment mixin for payment records.

Uses SQLAlchemy's declared_attr pattern so columns are automatically
created when the mixin is inherited.
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON
from sqlalchemy.orm import declared_attr


class PaymentMixin:
    """
    Mixin for Payment model.
    
    Tracks individual payment transactions.
    Columns are automatically created when you inherit this mixin.
    
    Note: You still need to define 'id' as primary key in your model.
    """
    
    # Core fields - using declared_attr for proper column creation
    @declared_attr
    def stripe_payment_intent_id(cls):
        return Column(String(255), unique=True, index=True)
    
    @declared_attr
    def stripe_invoice_id(cls):
        return Column(String(255), index=True)
    
    @declared_attr
    def user_id(cls):
        return Column(Integer, nullable=False, index=True)
    
    # Amount
    @declared_attr
    def amount(cls):
        return Column(Integer, nullable=False)  # in cents
    
    @declared_attr
    def currency(cls):
        return Column(String(3), default='usd', nullable=False)
    
    # Status: succeeded, pending, failed, canceled, refunded
    @declared_attr
    def status(cls):
        return Column(String(50), nullable=False)
    
    # Payment details
    @declared_attr
    def payment_method(cls):
        return Column(String(255))
    
    @declared_attr
    def receipt_url(cls):
        return Column(String(500))
    
    # Metadata
    @declared_attr
    def description(cls):
        return Column(Text)
    
    @declared_attr
    def payment_metadata(cls):
        """Named payment_metadata to avoid conflict with SQLAlchemy's metadata."""
        return Column(JSON)
    
    @declared_attr
    def created_at(cls):
        return Column(DateTime, default=datetime.utcnow, nullable=False)
    
    @declared_attr
    def updated_at(cls):
        return Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def to_dict(self):
        """Convert payment to dictionary."""
        return {
            'id': self.id,
            'stripe_payment_intent_id': self.stripe_payment_intent_id,
            'stripe_invoice_id': self.stripe_invoice_id,
            'user_id': self.user_id,
            'amount': self.amount,
            'currency': self.currency,
            'status': self.status,
            'payment_method': self.payment_method,
            'receipt_url': self.receipt_url,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f'<Payment {self.amount} {self.currency} status={self.status}>'

