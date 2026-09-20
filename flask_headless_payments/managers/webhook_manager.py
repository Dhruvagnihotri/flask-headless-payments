"""
flask_headless_payments.managers.webhook_manager
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Webhook event handling.
"""

import stripe
import time
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Callable, Optional
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)


def _json_safe(obj):
    """Recursively replace any Decimal in a (possibly nested) dict/list
    with str. Newer stripe-python parses some `*_decimal` fields (e.g.
    quantity_decimal on subscription items) as decimal.Decimal for
    precision — that's not JSON-serializable, so it still breaks the
    JSON-column insert even after `.to_dict()` (confirmed in production
    2026-09-06: "Object of type Decimal is not JSON serializable", on
    invoice.payment_succeeded / customer.subscription.created specifically).
    str() keeps the exact value (no float rounding); good enough for a
    stored audit column that's never used for arithmetic.
    """
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def _as_plain_dict(obj):
    """Normalize a Stripe API object to a plain, JSON-serializable dict.

    stripe-python's Event/Session/Subscription/Invoice objects are
    StripeObject instances, not dicts. Newer stripe-python releases
    dropped StripeObject's dict-compatible `.get()` (confirmed in
    production 2026-09-06 — every webhook delivery 500'd with "'get' is
    a dict method, but a Session is not a dict"), and a raw StripeObject
    also isn't JSON-serializable for storage in a JSON column. `.to_dict()`
    recursively converts nested StripeObjects/ListObjects too, so this is
    safe to call once at the boundary rather than patching every `.get()`
    call site. Left as a no-op for callers that already pass a plain dict
    (e.g. tests). Then run through _json_safe for the Decimal case above.
    """
    if hasattr(obj, 'to_dict'):
        obj = obj.to_dict()
    return _json_safe(obj)


class WebhookManager:
    """Manages Stripe webhook events with proper transaction handling."""
    
    def __init__(self, db, user_model, webhook_event_model, subscription_manager,
                 payment_model=None, subscription_event_model=None):
        """
        Initialize webhook manager.

        Args:
            db: SQLAlchemy database instance
            user_model: User model class
            webhook_event_model: WebhookEvent model class
            subscription_manager: SubscriptionManager instance
            payment_model: Payment model class (optional — without it,
                _handle_invoice_paid/_handle_payment_intent_succeeded log
                and skip instead of recording a Payment row)
            subscription_event_model: SubscriptionEvent model class (optional
                — without it, subscription created/updated/deleted handlers
                still update user_model's current-state fields exactly as
                before, they just skip appending a history row)
        """
        self.db = db
        self.user_model = user_model
        self.webhook_event_model = webhook_event_model
        self.subscription_manager = subscription_manager
        self.payment_model = payment_model
        self.subscription_event_model = subscription_event_model
        self.event_handlers = {}
        self.post_commit_callbacks = {}  # For business logic after successful commit
    
    def verify_webhook(self, payload: bytes, sig_header: str, webhook_secret: str) -> Optional[Dict[str, Any]]:
        """
        Verify webhook signature and construct event.
        
        Args:
            payload: Request body bytes
            sig_header: Stripe-Signature header
            webhook_secret: Webhook secret from Stripe
            
        Returns:
            dict: Stripe event object or None if verification fails
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
            return event
        except ValueError as e:
            logger.error(f"Invalid payload: {e}")
            return None
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid signature: {e}")
            return None
    
    def register_handler(self, event_type: str, handler: Callable):
        """
        Register a custom handler for an event type.
        
        IMPORTANT: Handlers should NOT commit the transaction.
        The webhook manager handles the commit after all processing is done.
        
        Args:
            event_type: Stripe event type (e.g., 'customer.subscription.created')
            handler: Handler function that takes (event_data, db, user_model, commit=False)
        """
        self.event_handlers[event_type] = handler
        logger.info(f"Registered custom handler for {event_type}")
    
    def register_post_commit_callback(self, event_type: str, callback: Callable):
        """
        Register a callback that runs AFTER successful webhook processing and commit.
        
        Use this for business logic that should only run after the webhook data
        is safely persisted (e.g., updating user quotas, sending emails, etc.).
        
        The callback receives: (event_data: dict, user_model: class, user: object|None)
        
        Example:
            def on_subscription_created(event_data, user_model, user):
                if user:
                    user.pdf_quota = 500
                    db.session.commit()
            
            webhook_manager.register_post_commit_callback(
                'customer.subscription.created',
                on_subscription_created
            )
        
        Args:
            event_type: Stripe event type
            callback: Callback function(event_data, user_model, user)
        """
        if event_type not in self.post_commit_callbacks:
            self.post_commit_callbacks[event_type] = []
        self.post_commit_callbacks[event_type].append(callback)
        logger.info(f"Registered post-commit callback for {event_type}")
    
    def process_event(self, event: Dict[str, Any], _max_deadlock_retries: int = 3) -> bool:
        """
        Process a webhook event, retrying on MySQL deadlock.

        The SELECT ... FOR UPDATE idempotency claim below (see
        _process_event_once) can deadlock under real concurrent access —
        confirmed while load-testing locally 2026-09-07: Stripe routinely
        fires 4-6 events within seconds of a single checkout completing
        (checkout.session.completed, customer.subscription.created,
        invoice.*, billing_portal.*), and near-simultaneous INSERTs
        against stripe_event_id's unique index hit InnoDB gap-lock
        contention. Without this retry, every such burst 500s on first
        attempt and only succeeds because Stripe happens to redeliver on
        failure — real behavior, but relying on Stripe's retry timing as
        the only safety net is fragile, not a fix. Production runs a
        single sync gunicorn worker today (no true request concurrency),
        so this is a latent risk rather than a confirmed prod failure —
        closing it now is cheap and removes the dependency on Stripe's
        retry behavior either way.
        """
        for attempt in range(_max_deadlock_retries):
            try:
                return self._process_event_once(event)
            except OperationalError as e:
                is_deadlock = '1213' in str(e) or 'Deadlock' in str(e)
                self.db.session.rollback()
                if not is_deadlock or attempt == _max_deadlock_retries - 1:
                    logger.error(
                        f"Failed to process event {event['id']} after "
                        f"{attempt + 1} attempt(s): {e}"
                    )
                    self._log_webhook_error(
                        event['id'], event['type'],
                        _as_plain_dict(event['data']['object']), str(e),
                    )
                    return False
                logger.warning(
                    f"Deadlock processing event {event['id']}, "
                    f"retrying (attempt {attempt + 2}/{_max_deadlock_retries})"
                )
                time.sleep(0.1 * (attempt + 1))
        return False

    def _process_event_once(self, event: Dict[str, Any]) -> bool:
        """
        Process a webhook event in a single transaction. One attempt —
        see process_event() above for the deadlock-retry wrapper callers
        should actually use.

        Transaction behavior:
        - All database operations happen in ONE transaction
        - On success: single commit at the end
        - On failure: full rollback, then error is logged separately

        Post-commit callbacks:
        - Run AFTER successful commit
        - Failures in callbacks don't affect the webhook processing
        - Each callback gets its own transaction for any DB operations

        Args:
            event: Stripe event object

        Returns:
            bool: True if processed successfully, False otherwise
        """
        event_type = event['type']
        event_data = _as_plain_dict(event['data']['object'])
        affected_user = None  # Track user for post-commit callbacks

        # Idempotency: Stripe redelivers events on transient handler
        # failures (e.g. our DB blip, our 5xx response). The unique
        # constraint on stripe_event_id would catch a true double-process
        # on commit, but by then we'd have re-run handlers, made
        # outbound Stripe API calls, and re-fired post-commit callbacks
        # (which DO write to the DB outside this transaction and would
        # double-count). We need a race-safe claim: SELECT ... FOR
        # UPDATE on the existing row blocks concurrent retries on the
        # same event_id while we decide whether to proceed.
        existing = self.webhook_event_model.query.filter_by(
            stripe_event_id=event['id']
        ).with_for_update().first()
        if existing is not None:
            if existing.processed:
                # Another worker won. Release the row lock by committing
                # the (empty) transaction and short-circuit.
                self.db.session.commit()
                logger.info(
                    f"Skipping duplicate webhook event {event['id']} "
                    f"({event_type}) — already processed at {existing.processed_at}"
                )
                return True
            # Previously errored OR concurrent retry. We hold the row
            # lock, so any other worker on the same event_id will block
            # until our transaction commits or rolls back. That worker
            # will then re-read with processed=True and short-circuit.
            logger.warning(
                f"Re-processing previously failed webhook event {event['id']} ({event_type})"
            )

        try:
            # Create webhook event record (will be committed with everything else)
            if existing is None:
                webhook_event = self.webhook_event_model(
                    stripe_event_id=event['id'],
                    event_type=event_type,
                    data=event_data,
                    received_at=datetime.utcnow()
                )
                self.db.session.add(webhook_event)
            else:
                # Reuse the row from the prior failed attempt. Refresh
                # event_type and data in case Stripe re-delivers a
                # corrected payload (rare but documented behavior).
                webhook_event = existing
                webhook_event.event_type = event_type
                webhook_event.data = event_data
                webhook_event.error = None  # clear stale error from prior attempt
            
            # Process the event - handlers should NOT commit
            if event_type in self.event_handlers:
                # Custom handlers receive commit=False to indicate they shouldn't commit
                self.event_handlers[event_type](event_data, self.db, self.user_model, commit=False)
            else:
                # Default handlers - get affected user for callbacks
                affected_user = self._handle_default_event(event_type, event_data, commit=False)
            
            # Mark as processed
            webhook_event.processed = True
            webhook_event.processed_at = datetime.utcnow()
            
            # SINGLE COMMIT for entire transaction
            self.db.session.commit()
            
            logger.info(f"Successfully processed event {event['id']} of type {event_type}")
            
            # Run post-commit callbacks (separate transactions for business logic)
            self._run_post_commit_callbacks(event_type, event_data, affected_user)
            
            return True

        except OperationalError:
            # Re-raise deadlocks (and any other OperationalError) so
            # process_event()'s wrapper can retry — rollback here so the
            # retry starts from a clean session, but don't log/swallow
            # it yet; the wrapper decides whether this was the last
            # attempt and only logs then.
            self.db.session.rollback()
            raise

        except Exception as e:
            # Full rollback on any other error
            self.db.session.rollback()

            logger.error(f"Failed to process event {event['id']}: {e}")

            # Log the error in a separate transaction
            self._log_webhook_error(event['id'], event_type, event_data, str(e))

            return False
    
    def _run_post_commit_callbacks(self, event_type: str, event_data: Dict[str, Any], user: Any):
        """
        Run post-commit callbacks for business logic.
        
        Each callback runs in its own context - failures don't affect other callbacks.
        """
        if event_type not in self.post_commit_callbacks:
            return
        
        for callback in self.post_commit_callbacks[event_type]:
            try:
                callback(event_data, self.user_model, user)
            except Exception as e:
                logger.error(f"Post-commit callback failed for {event_type}: {e}")
                # Don't re-raise - webhook was already processed successfully
    
    def _log_webhook_error(self, event_id: str, event_type: str, event_data: Dict[str, Any], error: str):
        """
        Log webhook error in a separate transaction.

        This ensures error logging doesn't fail due to the rolled-back transaction.
        Upsert-shaped: if the row already exists (e.g. this is a Stripe
        retry of a previously-errored event), update the existing row
        instead of inserting a duplicate that would violate the
        stripe_event_id unique constraint.
        """
        try:
            # Lock the row before reading state. Without FOR UPDATE the
            # check-then-write window lets a successful worker commit
            # processed=True between our read and our update — we'd
            # then overwrite the successful row with this error and
            # flip processed back to False. With FOR UPDATE we block
            # the success path's commit (or it blocks ours) so the
            # `if existing.processed` guard is safe.
            existing = self.webhook_event_model.query.filter_by(
                stripe_event_id=event_id
            ).with_for_update().first()
            if existing is not None:
                if existing.processed:
                    logger.info(
                        f"Skipping error-log upsert for event {event_id}: "
                        f"another worker already processed it successfully"
                    )
                    self.db.session.commit()
                    return
                existing.error = error
                existing.processed = False
            else:
                webhook_event = self.webhook_event_model(
                    stripe_event_id=event_id,
                    event_type=event_type,
                    data=event_data,
                    received_at=datetime.utcnow(),
                    processed=False,
                    error=error
                )
                self.db.session.add(webhook_event)
            self.db.session.commit()
        except Exception as log_error:
            logger.error(f"Failed to log webhook error: {log_error}")
            self.db.session.rollback()
    
    def _handle_default_event(self, event_type: str, event_data: Dict[str, Any], commit: bool = False) -> Optional[Any]:
        """
        Handle default events.
        
        Args:
            event_type: Event type
            event_data: Event data
            commit: Whether to commit (False when called from process_event)
            
        Returns:
            User object if found, for post-commit callbacks
        """
        user = None
        
        if event_type == 'checkout.session.completed':
            user = self._handle_checkout_completed(event_data, commit=commit)
        
        elif event_type == 'customer.subscription.created':
            user = self._handle_subscription_created(event_data, commit=commit)
        
        elif event_type == 'customer.subscription.updated':
            user = self._handle_subscription_updated(event_data, commit=commit)
        
        elif event_type == 'customer.subscription.deleted':
            user = self._handle_subscription_deleted(event_data, commit=commit)
        
        elif event_type == 'invoice.payment_succeeded':
            user = self._handle_invoice_paid(event_data, commit=commit)

        elif event_type == 'payment_intent.succeeded':
            user = self._handle_payment_intent_succeeded(event_data, commit=commit)

        elif event_type == 'invoice.payment_failed':
            user = self._handle_invoice_failed(event_data, commit=commit)

        else:
            logger.info(f"No default handler for event type: {event_type}")
        
        return user
    
    def _handle_checkout_completed(self, session: Dict[str, Any], commit: bool = False) -> Optional[Any]:
        """
        Handle checkout.session.completed event.
        
        Args:
            commit: Whether to commit (False when part of larger transaction)
            
        Returns:
            User object if found
        """
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        user = None
        
        if subscription_id:
            # Retrieve full subscription data
            subscription = stripe.Subscription.retrieve(subscription_id)
            
            # Find user by customer ID
            user = self.user_model.query.filter_by(stripe_customer_id=customer_id).first()
            if user:
                self.subscription_manager.update_user_subscription(user.id, subscription, commit=commit)
        
        return user
    
    def _handle_subscription_created(self, subscription: Dict[str, Any], commit: bool = False) -> Optional[Any]:
        """
        Handle customer.subscription.created event.
        
        Args:
            commit: Whether to commit (False when part of larger transaction)
            
        Returns:
            User object if found
        """
        customer_id = subscription.get('customer')

        # Find user by customer ID
        user = self.user_model.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            self.subscription_manager.update_user_subscription(user.id, subscription, commit=False)
            self._record_subscription_event(
                user=user,
                event_type='created',
                stripe_subscription_id=subscription.get('id'),
                plan_name=user.plan_name,
                plan_status=user.plan_status,
                current_period_start=user.current_period_start,
                current_period_end=user.current_period_end,
                cancel_at_period_end=user.cancel_at_period_end,
                commit=commit,
            )

        return user

    def _handle_subscription_updated(self, subscription: Dict[str, Any], commit: bool = False) -> Optional[Any]:
        """
        Handle customer.subscription.updated event.

        Args:
            commit: Whether to commit (False when part of larger transaction)

        Returns:
            User object if found
        """
        customer_id = subscription.get('customer')

        # Find user by customer ID
        user = self.user_model.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            self.subscription_manager.update_user_subscription(user.id, subscription, commit=False)
            self._record_subscription_event(
                user=user,
                event_type='updated',
                stripe_subscription_id=subscription.get('id'),
                plan_name=user.plan_name,
                plan_status=user.plan_status,
                current_period_start=user.current_period_start,
                current_period_end=user.current_period_end,
                cancel_at_period_end=user.cancel_at_period_end,
                commit=commit,
            )

        return user
    
    def _handle_subscription_deleted(self, subscription: Dict[str, Any], commit: bool = False) -> Optional[Any]:
        """
        Handle customer.subscription.deleted event.

        Args:
            commit: Whether to commit (False when part of larger transaction)

        Returns:
            User object if found
        """
        customer_id = subscription.get('customer')

        # Find user by customer ID
        user = self.user_model.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            # Stash the pre-cancel plan_status as a transient attribute so
            # post-commit callbacks can classify churn (trial vs paid)
            # accurately. We mutate user.plan_status to 'canceled' below;
            # by the time the callback runs, that mutation is committed
            # and the original signal is gone. SQLAlchemy ignores
            # underscore-prefixed attributes for ORM persistence so this
            # rides along on the in-memory object only.
            user._prev_plan_status = user.plan_status
            self._record_subscription_event(
                user=user,
                event_type='canceled',
                stripe_subscription_id=subscription.get('id') or user.stripe_subscription_id,
                plan_name=user.plan_name,
                plan_status='canceled',
                current_period_start=user.current_period_start,
                current_period_end=user.current_period_end,
                cancel_at_period_end=True,
                commit=False,
            )
            user.plan_status = 'canceled'
            user.stripe_subscription_id = None
            if commit:
                self.db.session.commit()

        return user

    def _record_subscription_event(self, *, user, event_type, stripe_subscription_id,
                                     plan_name=None, plan_status=None,
                                     current_period_start=None, current_period_end=None,
                                     cancel_at_period_end=None, commit=False):
        """
        Append a row to the subscription history ledger, if configured.

        Reads the just-applied current-state fields off `user` rather than
        re-parsing the raw Stripe payload — update_user_subscription()
        already did that extraction (UTC timestamp conversion, the
        price-metadata plan_name lookup), so this stays a pure snapshot of
        what was actually saved instead of a second, possibly-drifting
        interpretation of the same webhook.

        No-ops if the caller never configured a subscription_event_model
        (default is skipped entirely, matching payment_model's pattern in
        _upsert_payment_record).
        """
        if not self.subscription_event_model:
            return

        event = self.subscription_event_model(
            user_id=user.id,
            stripe_subscription_id=stripe_subscription_id,
            event_type=event_type,
            plan_name=plan_name,
            plan_status=plan_status,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            cancel_at_period_end=cancel_at_period_end,
        )
        self.db.session.add(event)
        if commit:
            self.db.session.commit()
        logger.info(
            f"Recorded subscription event: user={user.id} type={event_type} "
            f"subscription={stripe_subscription_id!r} plan={plan_name!r} status={plan_status!r}"
        )
        return event

    def _upsert_payment_record(self, *, user, payment_intent_id, invoice_id, amount, currency,
                                status, payment_method=None, receipt_url=None, description=None,
                                commit=False):
        """
        Get-or-create a Payment row, keyed by stripe_payment_intent_id.

        Confirmed in production (2026-09-19): invoice.payment_succeeded,
        payment_intent.succeeded, and charge.succeeded were ALL received
        and marked processed=True for real completed subscription
        payments — 1121 webhook events, 47 successful invoice payments —
        yet self.payment_model (paymentsvc_payments / the app's own
        override) had never once received a row. No default handler ever
        created one; every handler above only updates the User's
        subscription state. This is the fix.

        Keyed by payment_intent_id, not invoice_id, because a single
        subscription payment fires BOTH invoice.payment_succeeded and
        payment_intent.succeeded for the same underlying transaction —
        without a shared idempotent key, hooking both (needed to also
        cover one-time, non-invoice payments) would double-record every
        subscription payment. Whichever event arrives first creates the
        row; the second finds it via get_or_create and no-ops, in either
        delivery order.
        """
        if not self.payment_model:
            logger.info(
                f"No payment_model configured — skipping Payment record for "
                f"payment_intent={payment_intent_id!r} invoice={invoice_id!r}"
            )
            return

        query = self.payment_model.query
        existing = None
        if payment_intent_id:
            existing = query.filter_by(stripe_payment_intent_id=payment_intent_id).first()
        if existing is None and not payment_intent_id and invoice_id:
            # No payment_intent on this invoice (e.g. $0 invoice, or a
            # non-card payment method Stripe doesn't attach a PI to) —
            # fall back to invoice_id as the dedup key so it isn't silently
            # dropped, and so a retry of the same invoice doesn't duplicate.
            existing = query.filter_by(stripe_invoice_id=invoice_id).first()

        if existing:
            # Already recorded (e.g. the other event of the pair already
            # created it, or this is a Stripe redelivery). Keep it current
            # rather than silently ignoring a status change.
            existing.status = status
            if receipt_url:
                existing.receipt_url = receipt_url
            return existing

        payment = self.payment_model(
            stripe_payment_intent_id=payment_intent_id,
            stripe_invoice_id=invoice_id,
            user_id=user.id if user else None,
            amount=amount or 0,
            currency=currency or 'usd',
            status=status,
            payment_method=payment_method,
            receipt_url=receipt_url,
            description=description,
        )
        self.db.session.add(payment)
        if commit:
            self.db.session.commit()
        logger.info(
            f"Recorded payment: payment_intent={payment_intent_id!r} "
            f"invoice={invoice_id!r} amount={amount} {currency} status={status}"
        )
        return payment

    def _handle_invoice_paid(self, invoice: Dict[str, Any], commit: bool = False) -> Optional[Any]:
        """
        Handle invoice.payment_succeeded event — the canonical event for a
        completed subscription billing cycle (including the first invoice
        at subscription creation).

        Args:
            commit: Whether to commit (False when part of larger transaction)

        Returns:
            User object if found
        """
        customer_id = invoice.get('customer')
        user = self.user_model.query.filter_by(stripe_customer_id=customer_id).first() if customer_id else None

        self._upsert_payment_record(
            user=user,
            payment_intent_id=invoice.get('payment_intent'),
            invoice_id=invoice.get('id'),
            amount=invoice.get('amount_paid'),
            currency=invoice.get('currency'),
            status='succeeded',
            receipt_url=invoice.get('hosted_invoice_url'),
            description=invoice.get('description') or 'Subscription invoice payment',
            commit=commit,
        )

        logger.info(f"Invoice {invoice['id']} paid successfully")
        return user

    def _handle_payment_intent_succeeded(self, payment_intent: Dict[str, Any], commit: bool = False) -> Optional[Any]:
        """
        Handle payment_intent.succeeded event — the canonical event for a
        completed one-time ("payment" mode Checkout) payment that has no
        associated invoice. Also fires for subscription payments (which
        already have an invoice-keyed row from _handle_invoice_paid) —
        see _upsert_payment_record's docstring for how that's deduplicated.

        Args:
            commit: Whether to commit (False when part of larger transaction)

        Returns:
            User object if found
        """
        customer_id = payment_intent.get('customer')
        user = self.user_model.query.filter_by(stripe_customer_id=customer_id).first() if customer_id else None

        self._upsert_payment_record(
            user=user,
            payment_intent_id=payment_intent.get('id'),
            invoice_id=payment_intent.get('invoice'),
            amount=payment_intent.get('amount_received') or payment_intent.get('amount'),
            currency=payment_intent.get('currency'),
            status='succeeded',
            description=payment_intent.get('description'),
            commit=commit,
        )

        logger.info(f"PaymentIntent {payment_intent['id']} succeeded")
        return user

    def _handle_invoice_failed(self, invoice: Dict[str, Any], commit: bool = False) -> Optional[Any]:
        """
        Handle invoice.payment_failed event.
        
        Args:
            commit: Whether to commit (False when part of larger transaction)
            
        Returns:
            User object if found
        """
        customer_id = invoice.get('customer')
        user = self.user_model.query.filter_by(stripe_customer_id=customer_id).first() if customer_id else None

        self._upsert_payment_record(
            user=user,
            payment_intent_id=invoice.get('payment_intent'),
            invoice_id=invoice.get('id'),
            amount=invoice.get('amount_due'),
            currency=invoice.get('currency'),
            status='failed',
            description=invoice.get('description') or 'Subscription invoice payment failed',
            commit=commit,
        )

        logger.warning(f"Invoice {invoice['id']} payment failed")
        return user

