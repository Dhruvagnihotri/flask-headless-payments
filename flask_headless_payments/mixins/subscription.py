"""
flask_headless_payments.mixins.subscription
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Subscription mixin for User model.
"""

from datetime import datetime
from sqlalchemy import inspect


class SubscriptionMixin:
    """
    Mixin to add subscription capabilities to User model.
    
    Add this to your User model to get subscription tracking:
    
    Example:
        class User(db.Model, SubscriptionMixin):
            id = db.Column(db.Integer, primary_key=True)
            email = db.Column(db.String(255), unique=True)
    """
    
    # Stripe customer fields
    stripe_customer_id = None  # Will be added as column
    
    # Subscription fields
    stripe_subscription_id = None
    plan_name = None
    plan_status = None
    current_period_start = None
    current_period_end = None
    cancel_at_period_end = None
    
    # Trial fields
    trial_start = None
    trial_end = None
    
    # Metadata
    subscription_metadata = None
    
    def is_subscribed(self):
        """Check if user has an active subscription."""
        if not self.plan_status:
            return False
        return self.plan_status in ['active', 'trialing']
    
    def is_on_trial(self):
        """Check if user is on trial."""
        if not self.trial_end:
            return False
        return datetime.utcnow() < self.trial_end and self.plan_status == 'trialing'
    
    def has_plan(self, plan_name):
        """Check if user has a specific plan."""
        if not self.is_subscribed():
            return False
        return self.plan_name == plan_name
    
    def has_any_plan(self, plan_names):
        """Check if user has any of the specified plans."""
        if not self.is_subscribed():
            return False
        return self.plan_name in plan_names
    
    def subscription_active(self):
        """Check if subscription is currently active (not expired)."""
        if not self.is_subscribed():
            return False
        if not self.current_period_end:
            return False
        return datetime.utcnow() < self.current_period_end
    
    def days_until_renewal(self):
        """Get days until subscription renewal."""
        if not self.current_period_end:
            return None
        delta = self.current_period_end - datetime.utcnow()
        return max(0, delta.days)
    
    def to_subscription_dict(self):
        """Convert subscription info to dictionary."""
        return {
            'stripe_customer_id': self.stripe_customer_id,
            'stripe_subscription_id': self.stripe_subscription_id,
            'plan_name': self.plan_name,
            'plan_status': self.plan_status,
            'current_period_start': self.current_period_start.isoformat() if self.current_period_start else None,
            'current_period_end': self.current_period_end.isoformat() if self.current_period_end else None,
            'cancel_at_period_end': self.cancel_at_period_end,
            'trial_start': self.trial_start.isoformat() if self.trial_start else None,
            'trial_end': self.trial_end.isoformat() if self.trial_end else None,
            'is_subscribed': self.is_subscribed(),
            'is_on_trial': self.is_on_trial(),
            'days_until_renewal': self.days_until_renewal(),
        }
    
    def __repr__(self):
        return f'<Subscription plan={self.plan_name} status={self.plan_status}>'

