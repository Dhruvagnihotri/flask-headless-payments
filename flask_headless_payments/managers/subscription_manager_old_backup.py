"""
flask_headless_payments.managers.subscription_manager
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Subscription management logic.
"""

import stripe
import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """Manages subscription operations with Stripe."""
    
    def __init__(self, db, user_model, customer_model, payment_model):
        """
        Initialize subscription manager.
        
        Args:
            db: SQLAlchemy database instance
            user_model: User model class
            customer_model: Customer model class
            payment_model: Payment model class
        """
        self.db = db
        self.user_model = user_model
        self.customer_model = customer_model
        self.payment_model = payment_model
    
    def get_or_create_customer(self, user_id: int, email: str, name: Optional[str] = None) -> str:
        """
        Get existing Stripe customer or create new one.
        
        Args:
            user_id: User ID
            email: Customer email
            name: Customer name (optional)
            
        Returns:
            str: Stripe customer ID
        """
        # Check if customer exists in database
        customer = self.customer_model.query.filter_by(user_id=user_id).first()
        
        if customer:
            return customer.stripe_customer_id
        
        # Create new customer in Stripe
        try:
            stripe_customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={'user_id': user_id}
            )
            
            # Save to database
            customer = self.customer_model(
                stripe_customer_id=stripe_customer.id,
                user_id=user_id,
                email=email,
                name=name
            )
            self.db.session.add(customer)
            self.db.session.commit()
            
            logger.info(f"Created Stripe customer {stripe_customer.id} for user {user_id}")
            return stripe_customer.id
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Stripe customer: {e}")
            raise
    
    def create_subscription(self, customer_id: str, price_id: str, 
                          trial_days: Optional[int] = None,
                          metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Create a new subscription.
        
        Args:
            customer_id: Stripe customer ID
            price_id: Stripe price ID
            trial_days: Trial period in days (optional)
            metadata: Additional metadata (optional)
            
        Returns:
            dict: Subscription object
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
            
            subscription = stripe.Subscription.create(**subscription_params)
            
            logger.info(f"Created subscription {subscription.id} for customer {customer_id}")
            return subscription
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create subscription: {e}")
            raise
    
    def update_user_subscription(self, user_id: int, subscription_data: Dict[str, Any]) -> None:
        """
        Update user's subscription information in database.
        
        Args:
            user_id: User ID
            subscription_data: Subscription data from Stripe
        """
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
    
    def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> Dict[str, Any]:
        """
        Cancel a subscription.
        
        Args:
            subscription_id: Stripe subscription ID
            at_period_end: Cancel at period end (True) or immediately (False)
            
        Returns:
            dict: Canceled subscription object
        """
        try:
            if at_period_end:
                subscription = stripe.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=True
                )
                logger.info(f"Subscription {subscription_id} will cancel at period end")
            else:
                subscription = stripe.Subscription.delete(subscription_id)
                logger.info(f"Subscription {subscription_id} canceled immediately")
            
            return subscription
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to cancel subscription: {e}")
            raise
    
    def update_subscription(self, subscription_id: str, new_price_id: str) -> Dict[str, Any]:
        """
        Update subscription to new price/plan.
        
        Args:
            subscription_id: Stripe subscription ID
            new_price_id: New Stripe price ID
            
        Returns:
            dict: Updated subscription object
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
            )
            
            updated_subscription = stripe.Subscription.retrieve(subscription_id)
            logger.info(f"Updated subscription {subscription_id} to price {new_price_id}")
            
            return updated_subscription
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to update subscription: {e}")
            raise
    
    def get_subscription(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        """
        Get subscription from Stripe.
        
        Args:
            subscription_id: Stripe subscription ID
            
        Returns:
            dict: Subscription object or None
        """
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return subscription
        except stripe.error.StripeError as e:
            logger.error(f"Failed to retrieve subscription: {e}")
            return None

