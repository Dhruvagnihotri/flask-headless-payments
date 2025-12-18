"""
flask_headless_payments.managers.subscription_manager_unified
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unified production-grade subscription manager with full extensibility.

This is THE subscription manager - production-ready with hooks and events.
"""

import stripe
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.exc import SQLAlchemyError

from flask_headless_payments.utils.retry import retry_with_backoff, with_circuit_breaker
from flask_headless_payments.utils.monitoring import track_operation
from flask_headless_payments.extensibility import get_hook_manager, get_event_manager

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """
    Production-grade subscription manager with extensibility.
    
    Features:
    - ✅ Automatic retry with circuit breaker
    - ✅ Transaction handling with rollback
    - ✅ Idempotency support
    - ✅ Hook system for custom logic
    - ✅ Event system for notifications
    - ✅ Comprehensive error handling
    - ✅ Operation tracking
    
    Extension points:
    - Hooks: before_/after_ operations
    - Events: Published on state changes
    - Customizable via inheritance
    """
    
    def __init__(self, db, user_model, customer_model, payment_model, idempotency_manager=None):
        """
        Initialize subscription manager.
        
        Args:
            db: SQLAlchemy database instance
            user_model: User model class
            customer_model: Customer model class
            payment_model: Payment model class
            idempotency_manager: IdempotencyManager instance (optional)
        """
        self.db = db
        self.user_model = user_model
        self.customer_model = customer_model
        self.payment_model = payment_model
        self.idempotency_manager = idempotency_manager
        
        # Get extension managers
        self.hook_manager = get_hook_manager()
        self.event_manager = get_event_manager()
    
    @track_operation('get_or_create_customer')
    @retry_with_backoff(max_retries=3)
    @with_circuit_breaker
    def get_or_create_customer(
        self,
        user_id: int,
        email: str,
        name: Optional[str] = None,
        idempotency_key: Optional[str] = None
    ) -> str:
        """
        Get existing Stripe customer or create new one.
        
        Extension points:
        - Hook: before_customer_create
        - Hook: after_customer_create
        - Hook: customer_create_failed
        - Event: customer.created
        
        Args:
            user_id: User ID
            email: Customer email
            name: Customer name (optional)
            idempotency_key: Idempotency key (optional)
            
        Returns:
            str: Stripe customer ID
            
        Raises:
            stripe.error.StripeError: If Stripe API fails
            SQLAlchemyError: If database operation fails
        """
        try:
            # Check idempotency first
            if self.idempotency_manager and idempotency_key:
                is_duplicate, cached_result = self.idempotency_manager.is_duplicate(idempotency_key)
                if is_duplicate and cached_result:
                    logger.info(f"Returning cached customer for user {user_id}")
                    return cached_result.get('customer_id')
            
            # Check if customer exists in database
            customer = self.customer_model.query.filter_by(user_id=user_id).first()
            
            if customer:
                logger.info(f"Found existing customer {customer.stripe_customer_id} for user {user_id}")
                return customer.stripe_customer_id
            
            # HOOK: before_customer_create
            self.hook_manager.trigger(
                'before_customer_create',
                user_id=user_id,
                email=email,
                name=name
            )
            
            # Create new customer in Stripe
            stripe_customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={'user_id': user_id},
                idempotency_key=idempotency_key
            )
            
            # Save to database with transaction
            try:
                customer = self.customer_model(
                    stripe_customer_id=stripe_customer.id,
                    user_id=user_id,
                    email=email,
                    name=name
                )
                self.db.session.add(customer)
                self.db.session.commit()
                
                # Save idempotency result
                if self.idempotency_manager and idempotency_key:
                    self.idempotency_manager.save_result(
                        idempotency_key,
                        {'customer_id': stripe_customer.id},
                        user_id
                    )
                
                # HOOK: after_customer_create
                self.hook_manager.trigger(
                    'after_customer_create',
                    user_id=user_id,
                    customer_id=stripe_customer.id
                )
                
                # EVENT: customer.created
                self.event_manager.publish(
                    'customer.created',
                    {
                        'user_id': user_id,
                        'customer_id': stripe_customer.id,
                        'email': email
                    }
                )
                
                logger.info(f"Created Stripe customer {stripe_customer.id} for user {user_id}")
                return stripe_customer.id
                
            except SQLAlchemyError as e:
                self.db.session.rollback()
                
                # HOOK: customer_create_failed
                self.hook_manager.trigger(
                    'customer_create_failed',
                    user_id=user_id,
                    error=str(e),
                    stripe_customer_id=stripe_customer.id
                )
                
                logger.error(f"Database error creating customer: {e}")
                logger.error(f"CLEANUP REQUIRED: Stripe customer {stripe_customer.id} created but DB save failed")
                raise
            
        except stripe.error.StripeError as e:
            # HOOK: customer_create_failed
            self.hook_manager.trigger(
                'customer_create_failed',
                user_id=user_id,
                error=str(e)
            )
            
            logger.error(f"Stripe error creating customer: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating customer: {e}")
            raise
    
    @track_operation('create_subscription')
    @retry_with_backoff(max_retries=3)
    @with_circuit_breaker
    def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        trial_days: Optional[int] = None,
        metadata: Optional[Dict] = None,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new subscription.
        
        Extension points:
        - Hook: before_subscription_create
        - Hook: after_subscription_create
        - Hook: subscription_create_failed
        - Event: subscription.created
        
        Args:
            customer_id: Stripe customer ID
            price_id: Stripe price ID
            trial_days: Trial period in days (optional)
            metadata: Additional metadata (optional)
            idempotency_key: Idempotency key (optional)
            
        Returns:
            dict: Subscription object
            
        Raises:
            stripe.error.StripeError: If Stripe API fails
        """
        try:
            # HOOK: before_subscription_create
            self.hook_manager.trigger(
                'before_subscription_create',
                customer_id=customer_id,
                price_id=price_id,
                trial_days=trial_days
            )
            
            subscription_params = {
                'customer': customer_id,
                'items': [{'price': price_id}],
                'payment_behavior': 'default_incomplete',
                'expand': ['latest_invoice.payment_intent'],
            }
            
            if trial_days:
                subscription_params['trial_period_days'] = trial_days
            
            if metadata:
                subscription_params['metadata'] = metadata
            
            if idempotency_key:
                subscription_params['idempotency_key'] = idempotency_key
            
            subscription = stripe.Subscription.create(**subscription_params)
            
            # HOOK: after_subscription_create
            self.hook_manager.trigger(
                'after_subscription_create',
                subscription_id=subscription.id,
                customer_id=customer_id
            )
            
            # EVENT: subscription.created
            self.event_manager.publish(
                'subscription.created',
                {
                    'subscription_id': subscription.id,
                    'customer_id': customer_id,
                    'price_id': price_id,
                    'trial_days': trial_days
                }
            )
            
            logger.info(f"Created subscription {subscription.id} for customer {customer_id}")
            return subscription
            
        except stripe.error.StripeError as e:
            # HOOK: subscription_create_failed
            self.hook_manager.trigger(
                'subscription_create_failed',
                customer_id=customer_id,
                error=str(e)
            )
            
            logger.error(f"Stripe error creating subscription: {e}")
            raise
    
    @track_operation('update_user_subscription')
    def update_user_subscription(self, user_id: int, subscription_data: Dict[str, Any]) -> None:
        """
        Update user's subscription information.
        
        Extension points:
        - Event: subscription.updated
        
        Args:
            user_id: User ID
            subscription_data: Subscription data from Stripe
            
        Raises:
            SQLAlchemyError: If database operation fails
        """
        try:
            user = self.user_model.query.get(user_id)
            if not user:
                logger.error(f"User {user_id} not found")
                return
            
            # Update subscription fields
            user.stripe_subscription_id = subscription_data.get('id')
            user.plan_status = subscription_data.get('status')
            user.cancel_at_period_end = subscription_data.get('cancel_at_period_end', False)
            
            # Update period dates
            if subscription_data.get('current_period_start'):
                user.current_period_start = datetime.fromtimestamp(subscription_data['current_period_start'])
            if subscription_data.get('current_period_end'):
                user.current_period_end = datetime.fromtimestamp(subscription_data['current_period_end'])
            
            # Update trial dates
            if subscription_data.get('trial_start'):
                user.trial_start = datetime.fromtimestamp(subscription_data['trial_start'])
            if subscription_data.get('trial_end'):
                user.trial_end = datetime.fromtimestamp(subscription_data['trial_end'])
            
            # Extract plan name from metadata or items
            if subscription_data.get('items') and subscription_data['items'].get('data'):
                first_item = subscription_data['items']['data'][0]
                if first_item.get('price') and first_item['price'].get('metadata'):
                    user.plan_name = first_item['price']['metadata'].get('plan_name')
            
            self.db.session.commit()
            
            # EVENT: subscription.updated
            self.event_manager.publish(
                'subscription.updated',
                {
                    'user_id': user_id,
                    'subscription_id': subscription_data.get('id'),
                    'status': subscription_data.get('status')
                }
            )
            
            logger.info(f"Updated subscription for user {user_id}")
            
        except SQLAlchemyError as e:
            self.db.session.rollback()
            logger.error(f"Database error updating subscription: {e}")
            raise
        except Exception as e:
            self.db.session.rollback()
            logger.error(f"Unexpected error updating subscription: {e}")
            raise
    
    @track_operation('cancel_subscription')
    @retry_with_backoff(max_retries=3)
    @with_circuit_breaker
    def cancel_subscription(
        self,
        subscription_id: str,
        at_period_end: bool = True,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel a subscription.
        
        Extension points:
        - Hook: before_subscription_cancel
        - Hook: after_subscription_cancel
        - Event: subscription.cancelled
        
        Args:
            subscription_id: Stripe subscription ID
            at_period_end: Cancel at period end (True) or immediately (False)
            idempotency_key: Idempotency key (optional)
            
        Returns:
            dict: Canceled subscription object
            
        Raises:
            stripe.error.StripeError: If Stripe API fails
        """
        try:
            # HOOK: before_subscription_cancel
            self.hook_manager.trigger(
                'before_subscription_cancel',
                subscription_id=subscription_id,
                at_period_end=at_period_end
            )
            
            if at_period_end:
                subscription = stripe.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=True,
                    idempotency_key=idempotency_key
                )
                logger.info(f"Subscription {subscription_id} will cancel at period end")
            else:
                subscription = stripe.Subscription.delete(
                    subscription_id,
                    idempotency_key=idempotency_key
                )
                logger.info(f"Subscription {subscription_id} canceled immediately")
            
            # HOOK: after_subscription_cancel
            self.hook_manager.trigger(
                'after_subscription_cancel',
                subscription_id=subscription_id
            )
            
            # EVENT: subscription.cancelled
            self.event_manager.publish(
                'subscription.cancelled',
                {
                    'subscription_id': subscription_id,
                    'at_period_end': at_period_end
                }
            )
            
            return subscription
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error canceling subscription: {e}")
            raise
    
    @track_operation('update_subscription')
    @retry_with_backoff(max_retries=3)
    @with_circuit_breaker
    def update_subscription(
        self,
        subscription_id: str,
        new_price_id: str,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update subscription to new price/plan.
        
        Extension points:
        - Hook: before_subscription_update
        - Hook: after_subscription_update
        - Event: plan.upgraded or plan.downgraded
        
        Args:
            subscription_id: Stripe subscription ID
            new_price_id: New Stripe price ID
            idempotency_key: Idempotency key (optional)
            
        Returns:
            dict: Updated subscription object
            
        Raises:
            stripe.error.StripeError: If Stripe API fails
        """
        try:
            # HOOK: before_subscription_update
            self.hook_manager.trigger(
                'before_subscription_update',
                subscription_id=subscription_id,
                new_price_id=new_price_id
            )
            
            # Get current subscription
            subscription = stripe.Subscription.retrieve(subscription_id)
            
            # Update the subscription item
            stripe.Subscription.modify(
                subscription_id,
                items=[{
                    'id': subscription['items']['data'][0].id,
                    'price': new_price_id,
                }],
                proration_behavior='always_invoice',
                idempotency_key=idempotency_key
            )
            
            updated_subscription = stripe.Subscription.retrieve(subscription_id)
            
            # HOOK: after_subscription_update
            self.hook_manager.trigger(
                'after_subscription_update',
                subscription_id=subscription_id
            )
            
            # EVENT: plan.upgraded or plan.downgraded (users can determine which)
            self.event_manager.publish(
                'subscription.updated',
                {
                    'subscription_id': subscription_id,
                    'new_price_id': new_price_id
                }
            )
            
            logger.info(f"Updated subscription {subscription_id} to price {new_price_id}")
            
            return updated_subscription
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error updating subscription: {e}")
            raise

