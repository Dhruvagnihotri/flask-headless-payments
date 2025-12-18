"""
flask_headless_payments.utils.idempotency
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Idempotency key management for Stripe operations.
"""

import uuid
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class IdempotencyManager:
    """
    Manages idempotency keys for Stripe operations.
    
    Ensures operations can be safely retried without duplication.
    """
    
    def __init__(self, db):
        """
        Initialize idempotency manager.
        
        Args:
            db: SQLAlchemy database instance
        """
        self.db = db
        self._create_idempotency_table()
    
    def _create_idempotency_table(self):
        """Create idempotency keys table if it doesn't exist."""
        # Table will be created via models
        pass
    
    def generate_key(
        self,
        operation: str,
        user_id: int,
        params: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate idempotency key for operation.
        
        Args:
            operation: Operation name (e.g., 'create_subscription')
            user_id: User ID
            params: Additional parameters to include in key
        
        Returns:
            str: Idempotency key
        """
        # Create deterministic key from operation + user + params
        key_parts = [operation, str(user_id)]
        
        if params:
            # Sort params for deterministic hashing
            param_str = '|'.join(
                f"{k}:{v}" for k, v in sorted(params.items())
            )
            key_parts.append(param_str)
        
        # Hash to create key
        key_string = '|'.join(key_parts)
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:32]
        
        return f"paymentsvc_{key_hash}"
    
    def get_or_create_request_key(self, request_id: str) -> str:
        """
        Get or create idempotency key for HTTP request.
        
        Args:
            request_id: Unique request ID
        
        Returns:
            str: Idempotency key
        """
        return f"req_{request_id}"
    
    def is_duplicate(
        self,
        idempotency_key: str,
        max_age_hours: int = 24
    ) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if operation with key was recently executed.
        
        Args:
            idempotency_key: Idempotency key to check
            max_age_hours: Maximum age of cached result in hours
        
        Returns:
            tuple: (is_duplicate, cached_result)
        """
        try:
            # Query idempotency table
            from flask_headless_payments.models import get_idempotency_model
            IdempotencyKey = get_idempotency_model(self.db)
            
            cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
            
            record = IdempotencyKey.query.filter(
                IdempotencyKey.key == idempotency_key,
                IdempotencyKey.created_at >= cutoff
            ).first()
            
            if record:
                logger.info(f"Found duplicate operation: {idempotency_key}")
                return True, record.response_data
            
            return False, None
            
        except Exception as e:
            logger.error(f"Error checking idempotency: {e}")
            return False, None
    
    def save_result(
        self,
        idempotency_key: str,
        response_data: Dict[str, Any],
        user_id: Optional[int] = None
    ):
        """
        Save operation result for idempotency checking.
        
        Args:
            idempotency_key: Idempotency key
            response_data: Response data to cache
            user_id: User ID (optional)
        """
        try:
            from flask_headless_payments.models import get_idempotency_model
            IdempotencyKey = get_idempotency_model(self.db)
            
            record = IdempotencyKey(
                key=idempotency_key,
                response_data=response_data,
                user_id=user_id
            )
            
            self.db.session.add(record)
            self.db.session.commit()
            
            logger.info(f"Saved idempotency result: {idempotency_key}")
            
        except Exception as e:
            logger.error(f"Error saving idempotency result: {e}")
            self.db.session.rollback()
    
    def cleanup_old_keys(self, days: int = 7):
        """
        Clean up old idempotency keys.
        
        Args:
            days: Number of days to keep keys
        """
        try:
            from flask_headless_payments.models import get_idempotency_model
            IdempotencyKey = get_idempotency_model(self.db)
            
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            deleted = IdempotencyKey.query.filter(
                IdempotencyKey.created_at < cutoff
            ).delete()
            
            self.db.session.commit()
            
            logger.info(f"Cleaned up {deleted} old idempotency keys")
            
        except Exception as e:
            logger.error(f"Error cleaning up idempotency keys: {e}")
            self.db.session.rollback()

