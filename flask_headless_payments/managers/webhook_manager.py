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
    """Manages Stripe webhook events."""
    
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
        
        Args:
            event_type: Stripe event type (e.g., 'customer.subscription.created')
            handler: Handler function that takes (event_data, db, user_model)
        """
        self.event_handlers[event_type] = handler
        logger.info(f"Registered custom handler for {event_type}")
    
    def process_event(self, event: Dict[str, Any]) -> bool:
        """
        Process a webhook event.
        
        Args:
            event: Stripe event object
            
        Returns:
            bool: True if processed successfully, False otherwise
        """
        event_type = event['type']
        event_data = event['data']['object']
        
        # Save webhook event to database
        webhook_event = self.webhook_event_model(
            stripe_event_id=event['id'],
            event_type=event_type,
            data=event_data,
            received_at=datetime.utcnow()
        )
        self.db.session.add(webhook_event)
        self.db.session.commit()
        
        try:
            # Check for custom handler first
            if event_type in self.event_handlers:
                self.event_handlers[event_type](event_data, self.db, self.user_model)
            else:
                # Default handlers
                self._handle_default_event(event_type, event_data)
            
            # Mark as processed
            webhook_event.processed = True
            webhook_event.processed_at = datetime.utcnow()
            self.db.session.commit()
            
            logger.info(f"Successfully processed event {event['id']} of type {event_type}")
            return True
            
        except Exception as e:
            # Mark as failed with error
            webhook_event.error = str(e)
            self.db.session.commit()
            
            logger.error(f"Failed to process event {event['id']}: {e}")
            return False
    
    def _handle_default_event(self, event_type: str, event_data: Dict[str, Any]):
        """
        Handle default events.
        
        Args:
            event_type: Event type
            event_data: Event data
        """
        if event_type == 'checkout.session.completed':
            self._handle_checkout_completed(event_data)
        
        elif event_type == 'customer.subscription.created':
            self._handle_subscription_created(event_data)
        
        elif event_type == 'customer.subscription.updated':
            self._handle_subscription_updated(event_data)
        
        elif event_type == 'customer.subscription.deleted':
            self._handle_subscription_deleted(event_data)
        
        elif event_type == 'invoice.payment_succeeded':
            self._handle_invoice_paid(event_data)
        
        elif event_type == 'invoice.payment_failed':
            self._handle_invoice_failed(event_data)
        
        else:
            logger.info(f"No default handler for event type: {event_type}")
    
    def _handle_checkout_completed(self, session: Dict[str, Any]):
        """Handle checkout.session.completed event."""
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        
        if subscription_id:
            # Retrieve full subscription data
            subscription = stripe.Subscription.retrieve(subscription_id)
            
            # Find user by customer ID
            user = self.user_model.query.filter_by(stripe_customer_id=customer_id).first()
            if user:
                self.subscription_manager.update_user_subscription(user.id, subscription)
    
    def _handle_subscription_created(self, subscription: Dict[str, Any]):
        """Handle customer.subscription.created event."""
        customer_id = subscription.get('customer')
        
        # Find user by customer ID
        user = self.user_model.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            self.subscription_manager.update_user_subscription(user.id, subscription)
    
    def _handle_subscription_updated(self, subscription: Dict[str, Any]):
        """Handle customer.subscription.updated event."""
        customer_id = subscription.get('customer')
        
        # Find user by customer ID
        user = self.user_model.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            self.subscription_manager.update_user_subscription(user.id, subscription)
    
    def _handle_subscription_deleted(self, subscription: Dict[str, Any]):
        """Handle customer.subscription.deleted event."""
        customer_id = subscription.get('customer')
        
        # Find user by customer ID
        user = self.user_model.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            user.plan_status = 'canceled'
            user.stripe_subscription_id = None
            self.db.session.commit()
    
    def _handle_invoice_paid(self, invoice: Dict[str, Any]):
        """Handle invoice.payment_succeeded event."""
        logger.info(f"Invoice {invoice['id']} paid successfully")
    
    def _handle_invoice_failed(self, invoice: Dict[str, Any]):
        """Handle invoice.payment_failed event."""
        logger.warning(f"Invoice {invoice['id']} payment failed")

