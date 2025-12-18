"""
flask_headless_payments.managers.checkout_manager
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Checkout session management.
"""

import stripe
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class CheckoutManager:
    """Manages Stripe Checkout sessions."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize checkout manager.
        
        Args:
            config: Flask app configuration
        """
        self.config = config
        self.success_url = config.get('PAYMENTSVC_SUCCESS_URL', 'http://localhost:3000/success')
        self.cancel_url = config.get('PAYMENTSVC_CANCEL_URL', 'http://localhost:3000/cancel')
    
    def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        mode: str = 'subscription',
        trial_days: Optional[int] = None,
        metadata: Optional[Dict] = None,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a Stripe Checkout session.
        
        Args:
            customer_id: Stripe customer ID
            price_id: Stripe price ID
            mode: Checkout mode ('subscription' or 'payment')
            trial_days: Trial period in days (optional)
            metadata: Additional metadata (optional)
            success_url: Custom success URL (optional)
            cancel_url: Custom cancel URL (optional)
            
        Returns:
            dict: Checkout session object
        """
        try:
            session_params = {
                'customer': customer_id,
                'mode': mode,
                'line_items': [{'price': price_id, 'quantity': 1}],
                'success_url': success_url or self.success_url + '?session_id={CHECKOUT_SESSION_ID}',
                'cancel_url': cancel_url or self.cancel_url,
            }
            
            if mode == 'subscription' and trial_days:
                session_params['subscription_data'] = {
                    'trial_period_days': trial_days
                }
            
            if metadata:
                session_params['metadata'] = metadata
                if mode == 'subscription':
                    session_params['subscription_data'] = session_params.get('subscription_data', {})
                    session_params['subscription_data']['metadata'] = metadata
            
            session = stripe.checkout.Session.create(**session_params)
            
            logger.info(f"Created checkout session {session.id} for customer {customer_id}")
            return session
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create checkout session: {e}")
            raise
    
    def create_portal_session(
        self,
        customer_id: str,
        return_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a Stripe Customer Portal session.
        
        Args:
            customer_id: Stripe customer ID
            return_url: URL to return to after portal session
            
        Returns:
            dict: Portal session object
        """
        try:
            return_url = return_url or self.config.get('PAYMENTSVC_RETURN_URL', 'http://localhost:3000/account')
            
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            
            logger.info(f"Created portal session for customer {customer_id}")
            return session
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create portal session: {e}")
            raise
    
    def retrieve_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a checkout session.
        
        Args:
            session_id: Stripe session ID
            
        Returns:
            dict: Session object or None
        """
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            return session
        except stripe.error.StripeError as e:
            logger.error(f"Failed to retrieve session: {e}")
            return None

