"""
flask_headless_payments.mixins.payment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Payment mixin for payment records.
"""


class PaymentMixin:
    """
    Mixin for Payment model.
    
    Tracks individual payment transactions.
    """
    
    # Core fields
    id = None
    stripe_payment_intent_id = None
    stripe_invoice_id = None
    user_id = None
    
    # Amount
    amount = None
    currency = None
    
    # Status
    status = None  # succeeded, pending, failed, canceled, refunded
    
    # Payment details
    payment_method = None
    receipt_url = None
    
    # Metadata
    description = None
    metadata = None
    created_at = None
    updated_at = None
    
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

