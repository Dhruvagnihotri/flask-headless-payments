"""
flask_headless_payments.config
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Default configuration for Flask-PaymentSvc.
"""

DEFAULT_CONFIG = {
    # Core settings
    'PAYMENTSVC_URL_PREFIX': '/api/payments',
    'PAYMENTSVC_TABLE_PREFIX': 'paymentsvc',
    
    # Stripe settings
    'STRIPE_API_KEY': None,  # Must be set by user
    'STRIPE_WEBHOOK_SECRET': None,  # Must be set by user
    'STRIPE_API_VERSION': '2023-10-16',

    # Feature flags. PAYMENTSVC_ENABLE_USAGE_TRACKING is read by the
    # track_usage decorator (decorators.py). Removed PAYMENTSVC_ENABLE_TRIALS
    # and PAYMENTSVC_ENABLE_METERED_BILLING here 2026-09 — neither was ever
    # read anywhere in the codebase; they implied toggleable behavior that
    # didn't exist.
    'PAYMENTSVC_ENABLE_USAGE_TRACKING': True,

    # Plan configuration
    'PAYMENTSVC_DEFAULT_CURRENCY': 'usd',
    'PAYMENTSVC_DEFAULT_TRIAL_DAYS': 14,

    # Frontend URLs (for redirects)
    'PAYMENTSVC_SUCCESS_URL': 'http://localhost:3000/success',
    'PAYMENTSVC_CANCEL_URL': 'http://localhost:3000/cancel',
    'PAYMENTSVC_RETURN_URL': 'http://localhost:3000/account',

    # Security
    'PAYMENTSVC_CORS_ORIGINS': ['*'],
}

