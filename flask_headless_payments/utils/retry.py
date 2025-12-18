"""
flask_headless_payments.utils.retry
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Retry logic with exponential backoff for Stripe API calls.
"""

import time
import logging
from functools import wraps
from typing import Callable, Type, Tuple
import stripe

logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (
        stripe.error.RateLimitError,
        stripe.error.APIConnectionError,
        stripe.error.APIError,
    )
):
    """
    Decorator to retry function calls with exponential backoff.
    
    Usage:
        @retry_with_backoff(max_retries=3)
        def create_customer():
            return stripe.Customer.create(...)
    
    Args:
        max_retries: Maximum number of retry attempts
        backoff_factor: Multiplier for exponential backoff
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            delay = 1.0
            
            while retries <= max_retries:
                try:
                    return func(*args, **kwargs)
                    
                except exceptions as e:
                    retries += 1
                    
                    if retries > max_retries:
                        logger.error(
                            f"Failed after {max_retries} retries: {func.__name__}. Error: {e}"
                        )
                        raise
                    
                    # Calculate delay with jitter
                    jitter = delay * 0.1
                    sleep_time = delay + (jitter * (0.5 - time.time() % 1))
                    
                    logger.warning(
                        f"Retry {retries}/{max_retries} for {func.__name__} "
                        f"after {sleep_time:.2f}s. Error: {e}"
                    )
                    
                    time.sleep(sleep_time)
                    delay *= backoff_factor
                
                except Exception as e:
                    # Don't retry for non-retryable errors
                    logger.error(f"Non-retryable error in {func.__name__}: {e}")
                    raise
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


class CircuitBreaker:
    """
    Circuit breaker pattern for Stripe API calls.
    
    States: CLOSED (normal) -> OPEN (failing) -> HALF_OPEN (testing)
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        expected_exception: Type[Exception] = stripe.error.StripeError
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting half-open state
            expected_exception: Exception type to track
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func: Callable, *args, **kwargs):
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args, **kwargs: Function arguments
        
        Returns:
            Function result
        
        Raises:
            Exception: If circuit is open or function fails
        """
        if self.state == 'OPEN':
            if self._should_attempt_reset():
                self.state = 'HALF_OPEN'
                logger.info("Circuit breaker entering HALF_OPEN state")
            else:
                raise Exception("Circuit breaker is OPEN - requests blocked")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
            
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        """Handle successful call."""
        if self.state == 'HALF_OPEN':
            self.state = 'CLOSED'
            logger.info("Circuit breaker reset to CLOSED state")
        self.failure_count = 0
        self.last_failure_time = None
    
    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
            logger.error(
                f"Circuit breaker OPENED after {self.failure_count} failures"
            )
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        return (time.time() - self.last_failure_time) >= self.timeout


# Global circuit breaker instance
_stripe_circuit_breaker = CircuitBreaker()


def with_circuit_breaker(func: Callable):
    """
    Decorator to protect function with circuit breaker.
    
    Usage:
        @with_circuit_breaker
        def stripe_operation():
            return stripe.Customer.create(...)
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        return _stripe_circuit_breaker.call(func, *args, **kwargs)
    return wrapper

