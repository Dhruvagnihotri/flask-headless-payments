"""
Flask-Headless-Payments
~~~~~~~~~~~~~~~~~~~~~~~

Modern, headless payment integration for Flask APIs.

Basic usage:

    from flask import Flask
    from flask_headless_auth import AuthSvc
    from flask_headless_payments import PaymentSvc
    
    app = Flask(__name__)
    app.config['STRIPE_API_KEY'] = 'sk_test_...'
    app.config['STRIPE_WEBHOOK_SECRET'] = 'whsec_...'
    
    # Initialize auth (required)
    auth = AuthSvc(app)
    
    # Initialize payments
    payments = PaymentSvc(
        app,
        plans={
            'free': {'name': 'Free', 'price_id': None},
            'pro': {'name': 'Pro', 'price_id': 'price_xxx'},
        }
    )
    
    if __name__ == '__main__':
        app.run()

:copyright: (c) 2024 by Dhruv Agnihotri.
:license: MIT, see LICENSE for more details.
"""

from .core import PaymentSvc
from .__version__ import __version__

# Export mixins for users to create custom models
from .mixins import (
    SubscriptionMixin,
    CustomerMixin,
    PaymentMixin,
    WebhookEventMixin
)

# Export decorators for plan protection
from .decorators import (
    requires_plan,
    requires_active_subscription,
    requires_feature,
    track_usage
)

# Export extensibility system
from .extensibility import (
    hook,
    event,
    Plugin,
    HookManager,
    EventManager,
    PluginManager
)

# Export db for convenience
from .extensions import db

__all__ = [
    'PaymentSvc',
    'db',
    'SubscriptionMixin',
    'CustomerMixin',
    'PaymentMixin',
    'WebhookEventMixin',
    'requires_plan',
    'requires_active_subscription',
    'requires_feature',
    'track_usage',
    'hook',
    'event',
    'Plugin',
    'HookManager',
    'EventManager',
    'PluginManager',
    '__version__',
]

