"""
flask_headless_payments.managers.subscription_manager_prod
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Production-grade subscription management with retry logic and transactions.
"""

import stripe
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.exc import SQLAlchemyError
from flask_headless_payments.utils.retry import retry_with_backoff, with_circuit_breaker
from flask_headless_payments.utils.monitoring import track_operation

logger = logging.getLogger(__name__)


class SubscriptionManagerProd:
    """Production-grade subscription manager with resilience patterns."""
    
    def __init__(self, db, user_model, customer_model, payment_model, idempotency_manager=None):
        """
        Initialize subscription manager.
        
        Args:
            db: SQLAlchemy database instance
            user_model: User model class
            customer_model: Customer model class
            payment_model: Payment model class
            idempotency_manager: IdempotencyManager instance
        """
        self.db = db
        self.user_model = user_model
        self.customer_model = customer_model
        self.payment_model = payment_model
        self.idempotency_manager = idempotency_manager
    
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
        Get existing Stripe customer or create new one with idempotency.
        
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
                
                logger.info(f"Created Stripe customer {stripe_customer.id} for user {user_id}")
                return stripe_customer.id
                
            except SQLAlchemyError as e:
                self.db.session.rollback()
                logger.error(f"Database error creating customer: {e}")
                # Customer created in Stripe but DB failed - log for manual cleanup
                logger.error(f"CLEANUP REQUIRED: Stripe customer {stripe_customer.id} created but DB save failed")
                raise
            
        except stripe.error.StripeError as e:
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
        Create a new subscription with retry logic.
        
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
            
            logger.info(f"Created subscription {subscription.id} for customer {customer_id}")
            return subscription
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating subscription: {e}")
            raise
    
    @track_operation('update_user_subscription')
    def update_user_subscription(self, user_id: int, subscription_data: Dict[str, Any]) -> None:
        """
        Update user's subscription with transaction and rollback.
        
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
        Cancel a subscription with retry logic.
        
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
        Update subscription to new price/plan with retry logic.
        
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
            logger.info(f"Updated subscription {subscription_id} to price {new_price_id}")
            
            return updated_subscription
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error updating subscription: {e}")
            raise

