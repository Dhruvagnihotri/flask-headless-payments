"""
flask_headless_payments.managers.webhook_manager
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Webhook event handling.
"""

import stripe
import logging
from datetime import datetime
from typing import Dict, Any, Callable, Optional

logger = logging.getLogger(__name__)


class WebhookManager:
    """Manages Stripe webhook events with proper transaction handling."""
    
    def __init__(self, db, user_model, webhook_event_model, subscription_manager):
        """
        Initialize webhook manager.
        
        Args:
            db: SQLAlchemy database instance
            user_model: User model class
            webhook_event_model: WebhookEvent model class
            subscription_manager: SubscriptionManager instance
        """
        self.db = db
        self.user_model = user_model
        self.webhook_event_model = webhook_event_model
        self.subscription_manager = subscription_manager
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
    
    def process_event(self, event: Dict[str, Any]) -> bool:
        """
        Process a webhook event in a single transaction.
        
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
        event_data = event['data']['object']
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
            
        except Exception as e:
            # Full rollback on any error
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
            self.subscription_manager.update_user_subscription(user.id, subscription, commit=commit)
        
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
            self.subscription_manager.update_user_subscription(user.id, subscription, commit=commit)
        
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
            user.plan_status = 'canceled'
            user.stripe_subscription_id = None
            if commit:
                self.db.session.commit()

        return user
    
    def _handle_invoice_paid(self, invoice: Dict[str, Any], commit: bool = False) -> Optional[Any]:
        """
        Handle invoice.payment_succeeded event.
        
        Args:
            commit: Whether to commit (False when part of larger transaction)
            
        Returns:
            User object if found
        """
        customer_id = invoice.get('customer')
        user = self.user_model.query.filter_by(stripe_customer_id=customer_id).first() if customer_id else None
        logger.info(f"Invoice {invoice['id']} paid successfully")
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
        logger.warning(f"Invoice {invoice['id']} payment failed")
        return user

