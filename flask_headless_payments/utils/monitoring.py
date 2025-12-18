"""
flask_headless_payments.utils.monitoring
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Monitoring, health checks, and request tracking.
"""

import uuid
import time
import logging
from functools import wraps
from flask import request, g
from datetime import datetime

logger = logging.getLogger(__name__)


def request_id_middleware(app):
    """
    Add request ID tracking middleware.
    
    Usage:
        from flask_headless_payments.utils import request_id_middleware
        request_id_middleware(app)
    """
    
    @app.before_request
    def before_request():
        # Generate or use existing request ID
        request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        g.request_id = request_id
        g.request_start_time = time.time()
    
    @app.after_request
    def after_request(response):
        # Add request ID to response
        if hasattr(g, 'request_id'):
            response.headers['X-Request-ID'] = g.request_id
        
        # Log request duration
        if hasattr(g, 'request_start_time'):
            duration = (time.time() - g.request_start_time) * 1000
            logger.info(
                f"Request {g.request_id} completed in {duration:.2f}ms "
                f"- {request.method} {request.path} - Status: {response.status_code}"
            )
        
        return response
    
    logger.info("Request ID middleware installed")


def track_operation(operation_name: str):
    """
    Decorator to track operation metrics.
    
    Usage:
        @track_operation('create_subscription')
        def create_subscription():
            pass
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            request_id = getattr(g, 'request_id', 'unknown')
            
            try:
                logger.info(
                    f"[{request_id}] Starting operation: {operation_name}"
                )
                
                result = fn(*args, **kwargs)
                
                duration = (time.time() - start_time) * 1000
                logger.info(
                    f"[{request_id}] Completed operation: {operation_name} "
                    f"in {duration:.2f}ms"
                )
                
                return result
                
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                logger.error(
                    f"[{request_id}] Failed operation: {operation_name} "
                    f"after {duration:.2f}ms - Error: {e}"
                )
                raise
        
        return wrapper
    return decorator


class HealthCheck:
    """Health check system for the payment service."""
    
    def __init__(self, app, db):
        """
        Initialize health check.
        
        Args:
            app: Flask application
            db: Database instance
        """
        self.app = app
        self.db = db
        self.checks = {}
    
    def register_check(self, name: str, check_fn):
        """
        Register a custom health check.
        
        Args:
            name: Check name
            check_fn: Function that returns (bool, str) - (is_healthy, message)
        """
        self.checks[name] = check_fn
    
    def check_database(self) -> tuple[bool, str]:
        """Check database connectivity."""
        try:
            # Simple query to check connection
            self.db.session.execute('SELECT 1')
            return True, "Database connection OK"
        except Exception as e:
            return False, f"Database error: {str(e)}"
    
    def check_stripe(self) -> tuple[bool, str]:
        """Check Stripe API connectivity."""
        try:
            import stripe
            # Simple API call to verify connectivity
            stripe.Account.retrieve()
            return True, "Stripe API OK"
        except Exception as e:
            return False, f"Stripe API error: {str(e)}"
    
    def run_all_checks(self) -> dict:
        """
        Run all health checks.
        
        Returns:
            dict: Health check results
        """
        results = {
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'healthy',
            'checks': {}
        }
        
        # Built-in checks
        checks_to_run = {
            'database': self.check_database,
            'stripe': self.check_stripe,
            **self.checks
        }
        
        for name, check_fn in checks_to_run.items():
            try:
                is_healthy, message = check_fn()
                results['checks'][name] = {
                    'status': 'pass' if is_healthy else 'fail',
                    'message': message
                }
                
                if not is_healthy:
                    results['status'] = 'unhealthy'
                    
            except Exception as e:
                results['checks'][name] = {
                    'status': 'error',
                    'message': str(e)
                }
                results['status'] = 'unhealthy'
        
        return results

