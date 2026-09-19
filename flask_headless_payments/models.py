"""
flask_headless_payments.models
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Default model implementations using mixins.
These are used when users don't provide custom models.
"""

from datetime import datetime
from flask_headless_payments.mixins import (
    SubscriptionMixin, CustomerMixin, PaymentMixin, WebhookEventMixin
)

# Cache for default models - only create once per db instance
_default_models_cache = {}


def create_default_models(db):
    """
    Create default model classes using the provided db instance.

    Each of Customer/Payment/WebhookEvent/UsageRecord is skipped (returned
    as None, no table ever created) if a table by that exact name is
    already registered in db.metadata — i.e. the caller already defined
    its own custom model under that name. Previously these were always
    defined regardless of overrides: an app providing all four custom
    models (the common case — every real app in this ecosystem does)
    still got the full paymentsvc_* default set created via db.create_all()
    on every start, forever. Mirrors the same fix already applied to
    flask-headless-auth's create_default_models(), and the same
    already-established pattern this file's own IdempotencyKey removal
    (see below) responds to: don't ship dead tables by default.

    Args:
        db: SQLAlchemy database instance

    Returns:
        tuple: (Customer, Payment, WebhookEvent, UsageRecord)
        Any entry may be None if a same-named table already exists.
    """

    # Return cached models if already created for this db instance
    db_id = id(db)
    if db_id in _default_models_cache:
        return _default_models_cache[db_id]

    def _already_mapped(tablename):
        return tablename in db.metadata.tables

    Customer = None
    if not _already_mapped('paymentsvc_customers'):
        class Customer(db.Model, CustomerMixin):
            """Default Customer model for Stripe customers."""
            __tablename__ = 'paymentsvc_customers'

            id = db.Column(db.Integer, primary_key=True)
            stripe_customer_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
            user_id = db.Column(db.Integer, nullable=False, index=True)
            email = db.Column(db.String(255), nullable=False)
            name = db.Column(db.String(255))

            # Billing details
            payment_method_id = db.Column(db.String(255))
            default_payment_method = db.Column(db.String(255))
            invoice_prefix = db.Column(db.String(50))

            # Address
            address_line1 = db.Column(db.String(255))
            address_line2 = db.Column(db.String(255))
            address_city = db.Column(db.String(100))
            address_state = db.Column(db.String(100))
            address_postal_code = db.Column(db.String(20))
            address_country = db.Column(db.String(2))

            # Tax
            tax_exempt = db.Column(db.String(50))
            tax_ids = db.Column(db.JSON)

            # Metadata
            created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
            updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    Payment = None
    if not _already_mapped('paymentsvc_payments'):
        class Payment(db.Model, PaymentMixin):
            """Default Payment model for tracking payments."""
            __tablename__ = 'paymentsvc_payments'

            id = db.Column(db.Integer, primary_key=True)
            stripe_payment_intent_id = db.Column(db.String(255), unique=True, index=True)
            stripe_invoice_id = db.Column(db.String(255), index=True)
            user_id = db.Column(db.Integer, nullable=False, index=True)

            # Amount
            amount = db.Column(db.Integer, nullable=False)  # in cents
            currency = db.Column(db.String(3), default='usd', nullable=False)

            # Status
            status = db.Column(db.String(50), nullable=False)  # succeeded, pending, failed, canceled, refunded

            # Payment details
            payment_method = db.Column(db.String(255))
            receipt_url = db.Column(db.String(500))

            # Metadata (renamed from 'metadata' to avoid SQLAlchemy reserved name conflict)
            description = db.Column(db.Text)
            payment_metadata = db.Column(db.JSON)  # Renamed from 'metadata' to 'payment_metadata'
            created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
            updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    WebhookEvent = None
    if not _already_mapped('paymentsvc_webhook_events'):
        class WebhookEvent(db.Model, WebhookEventMixin):
            """Default WebhookEvent model for tracking Stripe webhooks."""
            __tablename__ = 'paymentsvc_webhook_events'

            id = db.Column(db.Integer, primary_key=True)
            stripe_event_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
            event_type = db.Column(db.String(100), nullable=False, index=True)

            # Event data
            data = db.Column(db.JSON, nullable=False)

            # Processing
            processed = db.Column(db.Boolean, default=False, nullable=False, index=True)
            processed_at = db.Column(db.DateTime)
            error = db.Column(db.Text)

            # Metadata
            received_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
            created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    UsageRecord = None
    if not _already_mapped('paymentsvc_usage_records'):
        class UsageRecord(db.Model):
            """Default UsageRecord model for metered billing."""
            __tablename__ = 'paymentsvc_usage_records'

            id = db.Column(db.Integer, primary_key=True)
            user_id = db.Column(db.Integer, nullable=False, index=True)
            subscription_item_id = db.Column(db.String(255), nullable=False)

            # Usage
            quantity = db.Column(db.Integer, nullable=False)
            action = db.Column(db.String(100), nullable=False)  # e.g., 'pdf_conversion', 'api_call'

            # Stripe
            stripe_usage_record_id = db.Column(db.String(255), unique=True)

            # Metadata (renamed to avoid SQLAlchemy reserved name conflict)
            timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
            usage_metadata = db.Column(db.JSON)  # Renamed from 'metadata' to 'usage_metadata'

    # Cache and return
    result = (Customer, Payment, WebhookEvent, UsageRecord)
    _default_models_cache[db_id] = result

    return result
