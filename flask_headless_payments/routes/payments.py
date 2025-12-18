"""
flask_headless_payments.routes.payments
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Payment API routes.
"""

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
import stripe
import logging

logger = logging.getLogger(__name__)


def create_payment_blueprint(
    user_model,
    customer_model,
    payment_model,
    webhook_event_model,
    subscription_manager,
    checkout_manager,
    webhook_manager,
    plan_manager,
    config,
    blueprint_name='paymentsvc'
):
    """
    Create payment blueprint with all routes.
    
    Args:
        user_model: User model class
        customer_model: Customer model class
        payment_model: Payment model class
        webhook_event_model: WebhookEvent model class
        subscription_manager: SubscriptionManager instance
        checkout_manager: CheckoutManager instance
        webhook_manager: WebhookManager instance
        plan_manager: PlanManager instance
        config: App configuration
        blueprint_name: Blueprint name (default: 'paymentsvc')
    
    Returns:
        Blueprint: Configured payment blueprint
    """
    
    bp = Blueprint(blueprint_name, __name__)
    
    # Configure Stripe
    stripe.api_key = config.get('STRIPE_API_KEY')
    
    @bp.route('/plans', methods=['GET'])
    def get_plans():
        """Get all available plans."""
        try:
            plans = plan_manager.get_all_plans()
            return jsonify({'plans': plans}), 200
        except Exception as e:
            logger.error(f"Error getting plans: {e}")
            return jsonify({'error': 'Failed to retrieve plans'}), 500
    
    @bp.route('/subscription', methods=['GET'])
    @jwt_required()
    def get_subscription():
        """Get current user's subscription."""
        try:
            identity = get_jwt_identity()
            # Handle both email (string) and ID (int) as JWT identity
            if isinstance(identity, str) and '@' in identity:
                user = user_model.query.filter_by(email=identity).first()
            else:
                user = user_model.query.get(identity)
            
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            if not hasattr(user, 'to_subscription_dict'):
                return jsonify({'error': 'User model does not support subscriptions'}), 400
            
            subscription_info = user.to_subscription_dict()
            return jsonify({'subscription': subscription_info}), 200
            
        except Exception as e:
            logger.error(f"Error getting subscription: {e}")
            return jsonify({'error': 'Failed to retrieve subscription'}), 500
    
    @bp.route('/checkout', methods=['POST'])
    @jwt_required()
    def create_checkout():
        """Create a Stripe Checkout session."""
        try:
            identity = get_jwt_identity()
            # Handle both email (string) and ID (int) as JWT identity
            if isinstance(identity, str) and '@' in identity:
                user = user_model.query.filter_by(email=identity).first()
            else:
                user = user_model.query.get(identity)
            
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            data = request.get_json()
            plan_name = data.get('plan')
            
            if not plan_name:
                return jsonify({'error': 'Plan name is required'}), 400
            
            # Validate plan
            if not plan_manager.plan_exists(plan_name):
                return jsonify({'error': 'Invalid plan'}), 400
            
            # Get price ID
            price_id = plan_manager.get_price_id(plan_name)
            if not price_id:
                return jsonify({'error': 'Plan has no price ID'}), 400
            
            # Get or create Stripe customer
            customer_id = subscription_manager.get_or_create_customer(
                user_id=user.id,
                email=user.email,
                name=getattr(user, 'first_name', None)
            )
            
            # Update user with customer ID if not set
            if not hasattr(user, 'stripe_customer_id') or not user.stripe_customer_id:
                user.stripe_customer_id = customer_id
                from flask_headless_payments.extensions import get_db
                db = get_db()
                db.session.commit()
            
            # Get trial days
            trial_days = data.get('trial_days') or config.get('PAYMENTSVC_DEFAULT_TRIAL_DAYS')
            
            # Create checkout session
            session = checkout_manager.create_checkout_session(
                customer_id=customer_id,
                price_id=price_id,
                trial_days=trial_days,
                metadata={'user_id': user.id, 'plan_name': plan_name}
            )
            
            return jsonify({
                'session_id': session.id,
                'url': session.url
            }), 200
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {e}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Error creating checkout: {e}")
            return jsonify({'error': 'Failed to create checkout session'}), 500
    
    @bp.route('/portal', methods=['POST'])
    @jwt_required()
    def create_portal():
        """Create a Stripe Customer Portal session."""
        try:
            identity = get_jwt_identity()
            # Handle both email (string) and ID (int) as JWT identity
            if isinstance(identity, str) and '@' in identity:
                user = user_model.query.filter_by(email=identity).first()
            else:
                user = user_model.query.get(identity)
            
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            # Check if user has customer ID
            if not hasattr(user, 'stripe_customer_id') or not user.stripe_customer_id:
                return jsonify({'error': 'No active subscription found'}), 400
            
            # Create portal session
            session = checkout_manager.create_portal_session(
                customer_id=user.stripe_customer_id
            )
            
            return jsonify({'url': session.url}), 200
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {e}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Error creating portal session: {e}")
            return jsonify({'error': 'Failed to create portal session'}), 500
    
    @bp.route('/cancel', methods=['POST'])
    @jwt_required()
    def cancel_subscription():
        """Cancel user's subscription."""
        try:
            identity = get_jwt_identity()
            # Handle both email (string) and ID (int) as JWT identity
            if isinstance(identity, str) and '@' in identity:
                user = user_model.query.filter_by(email=identity).first()
            else:
                user = user_model.query.get(identity)
            
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            if not hasattr(user, 'stripe_subscription_id') or not user.stripe_subscription_id:
                return jsonify({'error': 'No active subscription found'}), 400
            
            data = request.get_json() or {}
            at_period_end = data.get('at_period_end', True)
            
            # Cancel subscription
            subscription = subscription_manager.cancel_subscription(
                subscription_id=user.stripe_subscription_id,
                at_period_end=at_period_end
            )
            
            # Update user
            subscription_manager.update_user_subscription(user.id, subscription)
            
            return jsonify({
                'message': 'Subscription canceled successfully',
                'cancel_at_period_end': subscription.get('cancel_at_period_end')
            }), 200
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {e}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Error canceling subscription: {e}")
            return jsonify({'error': 'Failed to cancel subscription'}), 500
    
    @bp.route('/upgrade', methods=['POST'])
    @jwt_required()
    def upgrade_plan():
        """Upgrade/downgrade subscription plan."""
        try:
            identity = get_jwt_identity()
            # Handle both email (string) and ID (int) as JWT identity
            if isinstance(identity, str) and '@' in identity:
                user = user_model.query.filter_by(email=identity).first()
            else:
                user = user_model.query.get(identity)
            
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            if not hasattr(user, 'stripe_subscription_id') or not user.stripe_subscription_id:
                return jsonify({'error': 'No active subscription found'}), 400
            
            data = request.get_json()
            new_plan = data.get('plan')
            
            if not new_plan:
                return jsonify({'error': 'New plan is required'}), 400
            
            # Validate plan
            if not plan_manager.plan_exists(new_plan):
                return jsonify({'error': 'Invalid plan'}), 400
            
            # Get price ID
            new_price_id = plan_manager.get_price_id(new_plan)
            if not new_price_id:
                return jsonify({'error': 'Plan has no price ID'}), 400
            
            # Update subscription
            subscription = subscription_manager.update_subscription(
                subscription_id=user.stripe_subscription_id,
                new_price_id=new_price_id
            )
            
            # Update user with new plan info
            user.plan_name = new_plan
            subscription_manager.update_user_subscription(user.id, subscription)
            
            return jsonify({
                'message': 'Subscription updated successfully',
                'new_plan': new_plan
            }), 200
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {e}")
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Error upgrading subscription: {e}")
            return jsonify({'error': 'Failed to upgrade subscription'}), 500
    
    @bp.route('/webhook', methods=['POST'])
    def webhook():
        """Handle Stripe webhook events."""
        payload = request.data
        sig_header = request.headers.get('Stripe-Signature')
        webhook_secret = config.get('STRIPE_WEBHOOK_SECRET')
        
        if not webhook_secret:
            logger.error("STRIPE_WEBHOOK_SECRET not configured")
            return jsonify({'error': 'Webhook not configured'}), 500
        
        # Verify webhook signature
        event = webhook_manager.verify_webhook(payload, sig_header, webhook_secret)
        
        if not event:
            return jsonify({'error': 'Invalid signature'}), 400
        
        # Process event
        success = webhook_manager.process_event(event)
        
        if success:
            return jsonify({'status': 'success'}), 200
        else:
            return jsonify({'error': 'Failed to process event'}), 500
    
    return bp

