"""
flask_headless_payments.utils.validation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Request validation schemas.
"""

from marshmallow import Schema, fields, validates, ValidationError, EXCLUDE
import logging

logger = logging.getLogger(__name__)


class CheckoutSchema(Schema):
    """Schema for checkout session creation."""
    
    class Meta:
        unknown = EXCLUDE
    
    plan = fields.Str(required=True)
    trial_days = fields.Int(required=False, allow_none=True)
    success_url = fields.URL(required=False, allow_none=True)
    cancel_url = fields.URL(required=False, allow_none=True)
    
    @validates('plan')
    def validate_plan(self, value):
        if not value or len(value) < 2:
            raise ValidationError('Plan name must be at least 2 characters')
        if len(value) > 50:
            raise ValidationError('Plan name must not exceed 50 characters')


class UpgradePlanSchema(Schema):
    """Schema for plan upgrade/downgrade."""
    
    class Meta:
        unknown = EXCLUDE
    
    plan = fields.Str(required=True)
    
    @validates('plan')
    def validate_plan(self, value):
        if not value or len(value) < 2:
            raise ValidationError('Plan name must be at least 2 characters')


class CancelSubscriptionSchema(Schema):
    """Schema for subscription cancellation."""
    
    class Meta:
        unknown = EXCLUDE
    
    at_period_end = fields.Bool(required=False, load_default=True)
    reason = fields.Str(required=False, allow_none=True)


def validate_request(schema_class):
    """
    Decorator to validate request data against schema.
    
    Usage:
        @validate_request(CheckoutSchema)
        def create_checkout():
            # request.validated_data contains validated data
            pass
    """
    from functools import wraps
    from flask import request, jsonify
    
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                # Get request data
                data = request.get_json() or {}
                
                # Validate
                schema = schema_class()
                validated_data = schema.load(data)
                
                # Attach to request
                request.validated_data = validated_data
                
                return fn(*args, **kwargs)
                
            except ValidationError as e:
                logger.warning(f"Validation error: {e.messages}")
                return jsonify({
                    'error': 'Validation failed',
                    'details': e.messages
                }), 400
            except Exception as e:
                logger.error(f"Unexpected validation error: {e}")
                return jsonify({'error': 'Invalid request'}), 400
        
        return wrapper
    return decorator

