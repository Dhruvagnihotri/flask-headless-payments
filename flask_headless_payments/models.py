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


def create_default_models(db, skip_customer=False, skip_payment=False,
                           skip_webhook_event=False, skip_usage_record=False,
                           skip_subscription_event=False):
    """
    Create default model classes using the provided db instance.

    Each of Customer/Payment/WebhookEvent/UsageRecord is skipped entirely
    (returned as None, no table ever created) when its skip_* flag is
    True — pass skip_X=True when the caller already provided its own
    X_model. This has to be an explicit flag, not a "does a table by this
    name already exist" guess: the defaults are hardcoded to
    paymentsvc_customers/paymentsvc_payments/etc, but real apps' custom
    models use their own names (pdfcourt's are bare 'customers',
    'payments', ...) — a name-based check would never match and the
    unused paymentsvc_* defaults would keep getting created regardless,
    which is exactly what was still happening after an earlier pass at
    this fix that only checked db.metadata.tables. The metadata check is
    kept too, as a second guard for the case where a custom model
    happens to reuse one of these exact table names.

    SubscriptionEvent is different from the other four: it's an
    append-only history ledger, not a current-state mirror, so there's
    no equivalent "the app already tracks this elsewhere" reason to skip
    it by default the way Customer often is. It only gets skipped when a
    custom subscription_event_model is explicitly provided.

    Args:
        db: SQLAlchemy database instance
        skip_customer: True if the caller provided its own customer_model
        skip_payment: True if the caller provided its own payment_model
        skip_webhook_event: True if the caller provided its own webhook_event_model
        skip_usage_record: True if the caller provided its own usage_record_model
        skip_subscription_event: True if the caller provided its own subscription_event_model

    Returns:
        tuple: (Customer, Payment, WebhookEvent, UsageRecord, SubscriptionEvent)
        Any entry may be None if skipped or a same-named table already exists.
    """

    # Return cached models if already created for this exact combination
    cache_key = (id(db), skip_customer, skip_payment, skip_webhook_event,
                 skip_usage_record, skip_subscription_event)
    if cache_key in _default_models_cache:
        return _default_models_cache[cache_key]

    def _already_mapped(tablename):
        return tablename in db.metadata.tables

    Customer = None
    if not skip_customer and not _already_mapped('paymentsvc_customers'):
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
    if not skip_payment and not _already_mapped('paymentsvc_payments'):
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
    if not skip_webhook_event and not _already_mapped('paymentsvc_webhook_events'):
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
    if not skip_usage_record and not _already_mapped('paymentsvc_usage_records'):
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

    SubscriptionEvent = None
    if not skip_subscription_event and not _already_mapped('paymentsvc_subscription_events'):
        class SubscriptionEvent(db.Model):
            """
            Append-only subscription history ledger — one row per
            customer.subscription.created/updated/deleted event, snapshotting
            the plan/status/period fields at that moment.

            Not a replacement for the current-state fields SubscriptionMixin
            puts on user_model (those stay the fast, zero-join, hot-path
            read — checked on every authenticated request in real apps, e.g.
            trial-expiry enforcement). This is the thing that's genuinely
            missing without a separate table: plan changes and renewal
            cycles get silently overwritten with no history, unlike trials
            (which the mixin/app pattern already tracks historically
            elsewhere) — "what plan was this user on in March" or "how many
            times has this subscription been modified" can't be answered
            from current-state columns alone. Mirrors the same
            get-or-create/webhook-driven population pattern as Payment.
            """
            __tablename__ = 'paymentsvc_subscription_events'

            id = db.Column(db.Integer, primary_key=True)
            user_id = db.Column(db.Integer, nullable=False, index=True)
            stripe_subscription_id = db.Column(db.String(255), index=True)

            # 'created' | 'updated' | 'canceled' — semantic, not the raw
            # Stripe event type (WebhookEvent already stores that verbatim;
            # duplicating it here would add nothing).
            event_type = db.Column(db.String(20), nullable=False, index=True)

            plan_name = db.Column(db.String(100))
            plan_status = db.Column(db.String(50))
            current_period_start = db.Column(db.DateTime)
            current_period_end = db.Column(db.DateTime)
            cancel_at_period_end = db.Column(db.Boolean)

            occurred_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

            def to_dict(self):
                return {
                    'id': self.id,
                    'user_id': self.user_id,
                    'stripe_subscription_id': self.stripe_subscription_id,
                    'event_type': self.event_type,
                    'plan_name': self.plan_name,
                    'plan_status': self.plan_status,
                    'current_period_start': self.current_period_start.isoformat() if self.current_period_start else None,
                    'current_period_end': self.current_period_end.isoformat() if self.current_period_end else None,
                    'cancel_at_period_end': self.cancel_at_period_end,
                    'occurred_at': self.occurred_at.isoformat() if self.occurred_at else None,
                }

    # Cache and return
    result = (Customer, Payment, WebhookEvent, UsageRecord, SubscriptionEvent)
    _default_models_cache[cache_key] = result

    return result
