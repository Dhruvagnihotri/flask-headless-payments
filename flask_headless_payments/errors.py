"""
flask_headless_payments.errors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Custom exceptions and error handlers.
"""

import logging
from flask import jsonify
from werkzeug.exceptions import HTTPException
import stripe

logger = logging.getLogger(__name__)


class PaymentError(Exception):
    """Base exception for payment-related errors."""
    
    def __init__(self, message: str, status_code: int = 500, payload=None):
        super().__init__()
        self.message = message
        self.status_code = status_code
        self.payload = payload
    
    def to_dict(self):
        rv = dict(self.payload or ())
        rv['error'] = self.message
        return rv


class StripeAPIError(PaymentError):
    """Stripe API error."""
    
    def __init__(self, message: str, stripe_error=None):
        super().__init__(message, status_code=502)
        self.stripe_error = stripe_error


class InvalidPlanError(PaymentError):
    """Invalid subscription plan."""
    
    def __init__(self, plan_name: str):
        super().__init__(f"Invalid plan: {plan_name}", status_code=400)


class SubscriptionNotFoundError(PaymentError):
    """Subscription not found."""
    
    def __init__(self, user_id: int):
        super().__init__(f"No subscription found for user {user_id}", status_code=404)


class IdempotencyError(PaymentError):
    """Idempotency key conflict."""
    
    def __init__(self, key: str):
        super().__init__(f"Idempotency key conflict: {key}", status_code=409)


def register_error_handlers(app, db_model=None):
    """
    Register error handlers with Flask app.

    Usage:
        from flask_headless_payments.errors import register_error_handlers
        register_error_handlers(app, db_model=user_model)

    db_model: any db.Model subclass already bound to the app's SQLAlchemy
        session (e.g. the user model). Optional, but strongly recommended
        — without it, a DB exception (e.g. a dropped connection) that
        reaches one of these handlers is logged and converted to a clean
        error response, but the SQLAlchemy session is left in a failed
        state: every subsequent query on that session raises
        PendingRollbackError, indefinitely, until the worker process
        restarts. Confirmed live in production (2026-09-17): one transient
        MySQL disconnect, caught here with no rollback, took the entire
        app down for every DB-touching request for 2.5+ hours until this
        fix. `db_model.query.session.rollback()` is the version-agnostic
        way to reach the app's real session from here — this module has
        no direct reference to the Flask-SQLAlchemy `db` instance itself
        (it belongs to the host app, not this package), and a bound
        model's `.query.session` is the one thing SQLAlchemy guarantees
        resolves to the actual live session regardless of Flask-SQLAlchemy
        version internals (verified directly: even though `Model.query.
        session is db.session` is False — different proxy objects — a
        rollback through either one fully resets the same underlying
        transaction, confirmed by querying through the other reference
        afterward).

    Calling .rollback() on an already-healthy session is a harmless
    no-op, so this runs unconditionally at the top of every handler
    below, not just the generic one — a DB-touching webhook handler that
    raises a StripeError, for instance, needs the same protection.
    """

    def _rollback_session():
        if db_model is None:
            return
        try:
            db_model.query.session.rollback()
        except Exception as rollback_error:
            # Must never raise from inside an error handler — that would
            # replace a clear error response with an unhandled exception.
            logger.error(f"Session rollback in error handler failed: {rollback_error}")

    @app.errorhandler(PaymentError)
    def handle_payment_error(error):
        """Handle custom payment errors."""
        _rollback_session()
        logger.error(f"Payment error: {error.message}")
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        return response

    @app.errorhandler(stripe.error.CardError)
    def handle_card_error(error):
        """Handle Stripe card errors."""
        _rollback_session()
        logger.warning(f"Card error: {error.user_message}")
        return jsonify({
            'error': 'Card error',
            'message': error.user_message,
            'type': 'card_error'
        }), 402

    @app.errorhandler(stripe.error.RateLimitError)
    def handle_rate_limit_error(error):
        """Handle Stripe rate limit errors."""
        _rollback_session()
        logger.error(f"Stripe rate limit error: {error}")
        return jsonify({
            'error': 'Rate limit exceeded',
            'message': 'Too many requests. Please try again later.',
            'type': 'rate_limit_error'
        }), 429

    @app.errorhandler(stripe.error.InvalidRequestError)
    def handle_invalid_request_error(error):
        """Handle Stripe invalid request errors."""
        _rollback_session()
        logger.error(f"Stripe invalid request: {error}")
        return jsonify({
            'error': 'Invalid request',
            'message': str(error),
            'type': 'invalid_request_error'
        }), 400

    @app.errorhandler(stripe.error.AuthenticationError)
    def handle_authentication_error(error):
        """Handle Stripe authentication errors."""
        _rollback_session()
        logger.critical(f"Stripe authentication error: {error}")
        return jsonify({
            'error': 'Authentication failed',
            'message': 'Payment service configuration error',
            'type': 'authentication_error'
        }), 500

    @app.errorhandler(stripe.error.APIConnectionError)
    def handle_connection_error(error):
        """Handle Stripe connection errors."""
        _rollback_session()
        logger.error(f"Stripe connection error: {error}")
        return jsonify({
            'error': 'Service unavailable',
            'message': 'Could not connect to payment service',
            'type': 'connection_error'
        }), 503

    @app.errorhandler(stripe.error.StripeError)
    def handle_stripe_error(error):
        """Handle generic Stripe errors."""
        _rollback_session()
        logger.error(f"Stripe error: {error}")
        return jsonify({
            'error': 'Payment service error',
            'message': 'An error occurred with the payment service',
            'type': 'stripe_error'
        }), 500

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        """Handle HTTP exceptions."""
        _rollback_session()
        return jsonify({
            'error': error.name,
            'message': error.description
        }), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """Handle unexpected errors."""
        _rollback_session()
        logger.exception(f"Unexpected error: {error}")
        return jsonify({
            'error': 'Internal server error',
            'message': 'An unexpected error occurred'
        }), 500

    logger.info("Error handlers registered" + (" (with DB session rollback)" if db_model is not None else " (no db_model provided — DB exceptions here will NOT roll back the session; pass db_model= to fix)"))

