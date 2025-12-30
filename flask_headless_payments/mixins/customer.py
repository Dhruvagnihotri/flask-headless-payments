"""
flask_headless_payments.mixins.customer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Customer mixin for tracking Stripe customer data.

Uses SQLAlchemy's declared_attr pattern so columns are automatically
created when the mixin is inherited.
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, JSON
from sqlalchemy.orm import declared_attr


class CustomerMixin:
    """
    Mixin for Stripe customer model.
    
    Stores customer information synced from Stripe.
    Columns are automatically created when you inherit this mixin.
    
    Note: You still need to define 'id' as primary key in your model.
    """
    
    # Core fields - using declared_attr for proper column creation
    @declared_attr
    def stripe_customer_id(cls):
        return Column(String(255), unique=True, nullable=False, index=True)
    
    @declared_attr
    def user_id(cls):
        return Column(Integer, nullable=False, index=True)
    
    @declared_attr
    def email(cls):
        return Column(String(255), nullable=False)
    
    @declared_attr
    def name(cls):
        return Column(String(255))
    
    # Billing details
    @declared_attr
    def payment_method_id(cls):
        return Column(String(255))
    
    @declared_attr
    def default_payment_method(cls):
        return Column(String(255))
    
    # Timestamps
    @declared_attr
    def created_at(cls):
        return Column(DateTime, default=datetime.utcnow, nullable=False)
    
    @declared_attr
    def updated_at(cls):
        return Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def to_dict(self):
        """Convert customer to dictionary."""
        return {
            'stripe_customer_id': self.stripe_customer_id,
            'user_id': self.user_id,
            'email': self.email,
            'name': self.name,
            'payment_method_id': self.payment_method_id,
        }
    
    def __repr__(self):
        return f'<Customer {self.email} stripe_id={self.stripe_customer_id}>'

