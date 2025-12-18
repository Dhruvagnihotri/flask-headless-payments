"""
flask_headless_payments.extensibility.plugins
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Plugin system for clean extensions.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class Plugin(ABC):
    """
    Base class for plugins.
    
    Create custom plugins by inheriting from this class.
    
    Example:
        class EmailNotificationPlugin(Plugin):
            name = 'email_notifications'
            version = '1.0.0'
            
            def on_load(self, payment_svc):
                self.payment_svc = payment_svc
                # Register hooks
                payment_svc.hook_manager.register('after_subscription_create')(
                    self.send_welcome_email
                )
            
            def send_welcome_email(self, **kwargs):
                user_id = kwargs.get('user_id')
                # Send email logic
    """
    
    name: str = None
    version: str = '1.0.0'
    description: str = None
    author: str = None
    
    def __init__(self):
        if not self.name:
            raise ValueError(f"Plugin must define 'name' attribute")
    
    @abstractmethod
    def on_load(self, payment_svc):
        """
        Called when plugin is loaded.
        
        Args:
            payment_svc: PaymentSvc instance
        """
        pass
    
    def on_unload(self):
        """Called when plugin is unloaded."""
        pass
    
    def get_config(self) -> Dict[str, Any]:
        """Get plugin configuration."""
        return {}


class PluginManager:
    """
    Manages plugins for the payment service.
    
    Example:
        plugin_manager = PluginManager(payment_svc)
        plugin_manager.register(EmailNotificationPlugin())
        plugin_manager.load_all()
    """
    
    def __init__(self, payment_svc):
        """
        Initialize plugin manager.
        
        Args:
            payment_svc: PaymentSvc instance
        """
        self.payment_svc = payment_svc
        self._plugins: Dict[str, Plugin] = {}
        self._loaded: Dict[str, bool] = {}
    
    def register(self, plugin: Plugin):
        """
        Register a plugin.
        
        Args:
            plugin: Plugin instance
        """
        if plugin.name in self._plugins:
            logger.warning(f"Plugin '{plugin.name}' already registered, replacing")
        
        self._plugins[plugin.name] = plugin
        self._loaded[plugin.name] = False
        
        logger.info(
            f"Registered plugin: {plugin.name} v{plugin.version} "
            f"by {plugin.author or 'Unknown'}"
        )
    
    def load(self, plugin_name: str):
        """
        Load a specific plugin.
        
        Args:
            plugin_name: Name of plugin to load
        """
        if plugin_name not in self._plugins:
            raise ValueError(f"Plugin '{plugin_name}' not registered")
        
        if self._loaded[plugin_name]:
            logger.warning(f"Plugin '{plugin_name}' already loaded")
            return
        
        plugin = self._plugins[plugin_name]
        
        try:
            plugin.on_load(self.payment_svc)
            self._loaded[plugin_name] = True
            logger.info(f"Loaded plugin: {plugin_name}")
        except Exception as e:
            logger.error(f"Error loading plugin '{plugin_name}': {e}")
            raise
    
    def unload(self, plugin_name: str):
        """
        Unload a plugin.
        
        Args:
            plugin_name: Name of plugin to unload
        """
        if plugin_name not in self._plugins:
            raise ValueError(f"Plugin '{plugin_name}' not registered")
        
        if not self._loaded[plugin_name]:
            return
        
        plugin = self._plugins[plugin_name]
        
        try:
            plugin.on_unload()
            self._loaded[plugin_name] = False
            logger.info(f"Unloaded plugin: {plugin_name}")
        except Exception as e:
            logger.error(f"Error unloading plugin '{plugin_name}': {e}")
    
    def load_all(self):
        """Load all registered plugins."""
        for plugin_name in self._plugins:
            if not self._loaded[plugin_name]:
                try:
                    self.load(plugin_name)
                except Exception as e:
                    logger.error(f"Failed to load plugin '{plugin_name}': {e}")
    
    def get_loaded_plugins(self) -> List[str]:
        """Get list of loaded plugin names."""
        return [name for name, loaded in self._loaded.items() if loaded]
    
    def get_plugin(self, plugin_name: str) -> Optional[Plugin]:
        """Get plugin instance by name."""
        return self._plugins.get(plugin_name)


# Example plugins for users to reference

class ExampleAuditPlugin(Plugin):
    """
    Example plugin that logs all subscription changes.
    
    Usage:
        plugin_manager.register(ExampleAuditPlugin())
        plugin_manager.load('audit_logger')
    """
    
    name = 'audit_logger'
    version = '1.0.0'
    description = 'Logs all subscription changes'
    author = 'Example'
    
    def on_load(self, payment_svc):
        from flask_headless_payments.extensibility import get_event_manager
        event_manager = get_event_manager()
        
        # Subscribe to events
        event_manager.subscribe('subscription.created')(self.log_subscription_created)
        event_manager.subscribe('subscription.cancelled')(self.log_subscription_cancelled)
    
    def log_subscription_created(self, event):
        logger.info(f"AUDIT: Subscription created - {event.data}")
    
    def log_subscription_cancelled(self, event):
        logger.info(f"AUDIT: Subscription cancelled - {event.data}")


class ExampleMetricsPlugin(Plugin):
    """
    Example plugin for collecting custom metrics.
    
    Usage:
        plugin_manager.register(ExampleMetricsPlugin())
        plugin_manager.load('metrics_collector')
    """
    
    name = 'metrics_collector'
    version = '1.0.0'
    description = 'Collects subscription metrics'
    author = 'Example'
    
    def __init__(self):
        super().__init__()
        self.metrics = {
            'subscriptions_created': 0,
            'subscriptions_cancelled': 0,
            'payments_succeeded': 0,
            'payments_failed': 0
        }
    
    def on_load(self, payment_svc):
        from flask_headless_payments.extensibility import get_event_manager
        event_manager = get_event_manager()
        
        event_manager.subscribe('subscription.created')(self.count_subscription)
        event_manager.subscribe('subscription.cancelled')(self.count_cancellation)
        event_manager.subscribe('payment.succeeded')(self.count_payment_success)
        event_manager.subscribe('payment.failed')(self.count_payment_failure)
    
    def count_subscription(self, event):
        self.metrics['subscriptions_created'] += 1
    
    def count_cancellation(self, event):
        self.metrics['subscriptions_cancelled'] += 1
    
    def count_payment_success(self, event):
        self.metrics['payments_succeeded'] += 1
    
    def count_payment_failure(self, event):
        self.metrics['payments_failed'] += 1
    
    def get_metrics(self):
        return self.metrics

