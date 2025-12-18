"""
flask_headless_payments.mixins.customer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Customer mixin for tracking Stripe customer data.
"""


class CustomerMixin:
    """
    Mixin for Stripe customer model.
    
    Stores customer information synced from Stripe.
    """
    
    # Core fields
    id = None
    stripe_customer_id = None
    user_id = None
    email = None
    name = None
    
    # Billing details
    payment_method_id = None
    default_payment_method = None
    invoice_prefix = None
    
    # Address
    address_line1 = None
    address_line2 = None
    address_city = None
    address_state = None
    address_postal_code = None
    address_country = None
    
    # Tax
    tax_exempt = None
    tax_ids = None
    
    # Metadata
    created_at = None
    updated_at = None
    
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

