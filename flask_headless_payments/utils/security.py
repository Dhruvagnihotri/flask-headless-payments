"""
flask_headless_payments.utils.security
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Security utilities including webhook replay protection.
"""

import hmac
import hashlib
import time
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class WebhookReplayProtection:
    """
    Protects against webhook replay attacks.
    
    Tracks processed webhook IDs and timestamps to prevent duplicates.
    """
    
    def __init__(self, db, max_age_hours: int = 24):
        """
        Initialize replay protection.
        
        Args:
            db: Database instance
            max_age_hours: Maximum age of webhooks to track
        """
        self.db = db
        self.max_age_hours = max_age_hours
    
    def is_duplicate(self, event_id: str) -> bool:
        """
        Check if webhook event was already processed.
        
        Args:
            event_id: Stripe event ID
        
        Returns:
            bool: True if duplicate
        """
        try:
            from flask_headless_payments.extensions import get_db
            db = get_db()
            
            # Check if event exists in database
            from sqlalchemy import text
            result = db.session.execute(
                text("SELECT id FROM paymentsvc_webhook_events WHERE stripe_event_id = :event_id"),
                {"event_id": event_id}
            ).first()
            
            if result:
                logger.warning(f"Duplicate webhook detected: {event_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking webhook duplicate: {e}")
            # Fail safe - assume not duplicate if we can't check
            return False
    
    def verify_timestamp(
        self,
        timestamp: int,
        tolerance_seconds: int = 300
    ) -> bool:
        """
        Verify webhook timestamp is within acceptable range.
        
        Args:
            timestamp: Webhook timestamp
            tolerance_seconds: Acceptable time difference in seconds
        
        Returns:
            bool: True if timestamp is valid
        """
        current_time = int(time.time())
        time_diff = abs(current_time - timestamp)
        
        if time_diff > tolerance_seconds:
            logger.warning(
                f"Webhook timestamp outside tolerance: "
                f"diff={time_diff}s, tolerance={tolerance_seconds}s"
            )
            return False
        
        return True
    
    def verify_signature(
        self,
        payload: bytes,
        signature: str,
        secret: str
    ) -> bool:
        """
        Verify webhook signature using HMAC.
        
        Args:
            payload: Request body
            signature: Signature from header
            secret: Webhook secret
        
        Returns:
            bool: True if signature is valid
        """
        try:
            # Stripe signature format: t=timestamp,v1=signature
            sig_parts = {
                k: v for k, v in
                [part.split('=', 1) for part in signature.split(',')]
            }
            
            timestamp = int(sig_parts.get('t', 0))
            signature_v1 = sig_parts.get('v1', '')
            
            # Verify timestamp
            if not self.verify_timestamp(timestamp):
                return False
            
            # Compute expected signature
            signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
            expected_sig = hmac.new(
                secret.encode('utf-8'),
                signed_payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Constant-time comparison
            return hmac.compare_digest(expected_sig, signature_v1)
            
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return False
    
    def cleanup_old_records(self):
        """Clean up old webhook records."""
        try:
            from flask_headless_payments.extensions import get_db
            db = get_db()
            
            cutoff = datetime.utcnow() - timedelta(hours=self.max_age_hours)
            
            from sqlalchemy import text
            result = db.session.execute(
                text(
                    "DELETE FROM paymentsvc_webhook_events "
                    "WHERE processed = TRUE AND received_at < :cutoff"
                ),
                {"cutoff": cutoff}
            )
            
            db.session.commit()
            
            logger.info(f"Cleaned up {result.rowcount} old webhook records")
            
        except Exception as e:
            logger.error(f"Error cleaning up webhook records: {e}")
            db.session.rollback()


def rate_limit_by_user(limit: int = 100, window_seconds: int = 3600):
    """
    Rate limiting decorator by user ID.
    
    Usage:
        @rate_limit_by_user(limit=10, window_seconds=60)
        def create_checkout():
            pass
    
    Args:
        limit: Maximum requests per window
        window_seconds: Time window in seconds
    """
    from functools import wraps
    from flask import jsonify
    from flask_jwt_extended import get_jwt_identity
    
    # Simple in-memory store (use Redis in production)
    _rate_limit_store = {}
    
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user_id = get_jwt_identity()
            now = time.time()
            key = f"rate_limit:{user_id}"
            
            # Get or initialize request history
            if key not in _rate_limit_store:
                _rate_limit_store[key] = []
            
            # Remove old requests outside window
            _rate_limit_store[key] = [
                req_time for req_time in _rate_limit_store[key]
                if now - req_time < window_seconds
            ]
            
            # Check limit
            if len(_rate_limit_store[key]) >= limit:
                logger.warning(f"Rate limit exceeded for user {user_id}")
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'retry_after': window_seconds
                }), 429
            
            # Add current request
            _rate_limit_store[key].append(now)
            
            return fn(*args, **kwargs)
        
        return wrapper
    return decorator

