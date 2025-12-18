"""
flask_headless_payments.extensibility.hooks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Hook system for extending functionality.
"""

import logging
from functools import wraps
from typing import Callable, Any, List, Dict, Optional

logger = logging.getLogger(__name__)


class HookManager:
    """
    Manages hooks for extending library functionality.
    
    Hooks allow users to inject custom logic at specific points.
    
    Example:
        @hook_manager.register('before_subscription_create')
        def custom_validation(customer_id, price_id, **kwargs):
            # Your custom logic
            if not is_valid(price_id):
                raise ValueError("Invalid price")
    """
    
    def __init__(self):
        self._hooks: Dict[str, List[Callable]] = {}
    
    def register(self, hook_name: str, priority: int = 50):
        """
        Register a hook handler.
        
        Args:
            hook_name: Name of the hook
            priority: Execution priority (lower = earlier, default=50)
        
        Usage:
            @hook_manager.register('before_customer_create')
            def my_hook(user_id, email, **kwargs):
                print(f"Creating customer for {email}")
        """
        def decorator(func: Callable):
            if hook_name not in self._hooks:
                self._hooks[hook_name] = []
            
            self._hooks[hook_name].append({
                'func': func,
                'priority': priority
            })
            
            # Sort by priority
            self._hooks[hook_name].sort(key=lambda x: x['priority'])
            
            logger.info(f"Registered hook '{hook_name}': {func.__name__}")
            return func
        
        return decorator
    
    def trigger(self, hook_name: str, *args, **kwargs) -> List[Any]:
        """
        Trigger all handlers for a hook.
        
        Args:
            hook_name: Name of the hook to trigger
            *args, **kwargs: Arguments to pass to handlers
        
        Returns:
            list: Results from all handlers
        """
        if hook_name not in self._hooks:
            return []
        
        results = []
        for hook_info in self._hooks[hook_name]:
            try:
                func = hook_info['func']
                result = func(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Error in hook '{hook_name}': {e}")
                # Don't let hook errors break the flow
        
        return results
    
    def has_hooks(self, hook_name: str) -> bool:
        """Check if hook has any registered handlers."""
        return hook_name in self._hooks and len(self._hooks[hook_name]) > 0


# Global hook manager
_hook_manager = HookManager()


def hook(hook_name: str, priority: int = 50):
    """
    Decorator to register a hook handler.
    
    Usage:
        from flask_headless_payments.extensibility import hook
        
        @hook('before_subscription_create', priority=10)
        def my_validation(customer_id, price_id, **kwargs):
            # Your custom logic
            pass
    """
    return _hook_manager.register(hook_name, priority)


def get_hook_manager() -> HookManager:
    """Get global hook manager."""
    return _hook_manager


# Available hooks documentation
AVAILABLE_HOOKS = {
    # Customer hooks
    'before_customer_create': 'Before creating Stripe customer',
    'after_customer_create': 'After customer created (customer_id available)',
    'customer_create_failed': 'When customer creation fails',
    
    # Subscription hooks
    'before_subscription_create': 'Before creating subscription',
    'after_subscription_create': 'After subscription created',
    'subscription_create_failed': 'When subscription creation fails',
    
    'before_subscription_update': 'Before updating subscription',
    'after_subscription_update': 'After subscription updated',
    
    'before_subscription_cancel': 'Before canceling subscription',
    'after_subscription_cancel': 'After subscription canceled',
    
    # Webhook hooks
    'before_webhook_process': 'Before processing webhook',
    'after_webhook_process': 'After webhook processed',
    'webhook_process_failed': 'When webhook processing fails',
    
    # Payment hooks
    'payment_succeeded': 'When payment succeeds',
    'payment_failed': 'When payment fails',
    
    # General hooks
    'before_stripe_api_call': 'Before any Stripe API call',
    'after_stripe_api_call': 'After any Stripe API call',
    'stripe_api_error': 'When Stripe API call fails',
}

