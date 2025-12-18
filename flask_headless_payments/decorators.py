"""
flask_headless_payments.decorators
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Decorators for plan-based access control.
"""

from functools import wraps
from flask import jsonify, current_app
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
import logging

logger = logging.getLogger(__name__)


def requires_plan(*allowed_plans):
    """
    Decorator to require specific subscription plan(s).
    
    Usage:
        @app.route('/api/premium-feature')
        @jwt_required()
        @requires_plan('pro', 'enterprise')
        def premium_feature():
            return {'message': 'Premium content'}
    
    Args:
        *allowed_plans: Plan name(s) that are allowed to access the resource
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Verify JWT first
            verify_jwt_in_request()
            
            # Get current user ID from JWT
            user_id = get_jwt_identity()
            
            # Get payment service from app extensions
            payment_svc = current_app.extensions.get('paymentsvc')
            if not payment_svc:
                logger.error("PaymentSvc not initialized")
                return jsonify({'error': 'Payment service not available'}), 500
            
            # Get user
            user = payment_svc.user_model.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            # Check if user has subscription
            if not hasattr(user, 'is_subscribed') or not user.is_subscribed():
                return jsonify({
                    'error': 'Subscription required',
                    'message': 'This feature requires an active subscription',
                    'required_plans': list(allowed_plans)
                }), 403
            
            # Check if user's plan is in allowed plans
            if user.plan_name not in allowed_plans:
                return jsonify({
                    'error': 'Insufficient plan',
                    'message': f'This feature requires one of: {", ".join(allowed_plans)}',
                    'current_plan': user.plan_name,
                    'required_plans': list(allowed_plans)
                }), 403
            
            # User has valid plan, proceed
            return fn(*args, **kwargs)
        
        return wrapper
    return decorator


def requires_active_subscription(fn):
    """
    Decorator to require any active subscription.
    
    Usage:
        @app.route('/api/subscriber-only')
        @jwt_required()
        @requires_active_subscription
        def subscriber_feature():
            return {'message': 'Subscriber content'}
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # Verify JWT first
        verify_jwt_in_request()
        
        # Get current user ID from JWT
        user_id = get_jwt_identity()
        
        # Get payment service from app extensions
        payment_svc = current_app.extensions.get('paymentsvc')
        if not payment_svc:
            logger.error("PaymentSvc not initialized")
            return jsonify({'error': 'Payment service not available'}), 500
        
        # Get user
        user = payment_svc.user_model.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if user has active subscription
        if not hasattr(user, 'is_subscribed') or not user.is_subscribed():
            return jsonify({
                'error': 'Subscription required',
                'message': 'This feature requires an active subscription'
            }), 403
        
        # User has active subscription, proceed
        return fn(*args, **kwargs)
    
    return wrapper


def requires_feature(feature_name: str):
    """
    Decorator to require a specific feature in the user's plan.
    
    Usage:
        @app.route('/api/advanced-feature')
        @jwt_required()
        @requires_feature('advanced_editing')
        def advanced_feature():
            return {'message': 'Advanced feature'}
    
    Args:
        feature_name: Feature name to check
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Verify JWT first
            verify_jwt_in_request()
            
            # Get current user ID from JWT
            user_id = get_jwt_identity()
            
            # Get payment service from app extensions
            payment_svc = current_app.extensions.get('paymentsvc')
            if not payment_svc:
                logger.error("PaymentSvc not initialized")
                return jsonify({'error': 'Payment service not available'}), 500
            
            # Get user
            user = payment_svc.user_model.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            # Check if user has subscription
            if not hasattr(user, 'is_subscribed') or not user.is_subscribed():
                return jsonify({
                    'error': 'Subscription required',
                    'message': f'Feature "{feature_name}" requires an active subscription'
                }), 403
            
            # Check if plan has the feature
            plan_manager = payment_svc.plan_manager
            if not plan_manager.has_feature(user.plan_name, feature_name):
                return jsonify({
                    'error': 'Feature not available',
                    'message': f'Your plan does not include "{feature_name}"',
                    'current_plan': user.plan_name
                }), 403
            
            # User has feature, proceed
            return fn(*args, **kwargs)
        
        return wrapper
    return decorator


def track_usage(action: str, quantity: int = 1):
    """
    Decorator to track usage for metered billing.
    
    Usage:
        @app.route('/api/convert-pdf')
        @jwt_required()
        @track_usage('pdf_conversion', quantity=1)
        def convert_pdf():
            return {'message': 'PDF converted'}
    
    Args:
        action: Action name to track
        quantity: Quantity to track (default: 1)
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Execute the function first
            result = fn(*args, **kwargs)
            
            try:
                # Verify JWT
                verify_jwt_in_request()
                user_id = get_jwt_identity()
                
                # Get payment service
                payment_svc = current_app.extensions.get('paymentsvc')
                if payment_svc and payment_svc.config.get('PAYMENTSVC_ENABLE_USAGE_TRACKING'):
                    # Track usage in background
                    # You can implement actual usage tracking here
                    logger.info(f"Tracked usage: user={user_id}, action={action}, quantity={quantity}")
            except Exception as e:
                # Don't fail the request if usage tracking fails
                logger.error(f"Usage tracking failed: {e}")
            
            return result
        
        return wrapper
    return decorator

