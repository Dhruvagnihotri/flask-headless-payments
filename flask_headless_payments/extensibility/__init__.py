"""
flask_headless_payments.extensibility
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Extension system for customization and plugins.
"""

from .hooks import HookManager, hook, get_hook_manager
from .events import EventManager, event, get_event_manager
from .plugins import Plugin, PluginManager

__all__ = [
    'HookManager',
    'hook',
    'get_hook_manager',
    'EventManager', 
    'event',
    'get_event_manager',
    'Plugin',
    'PluginManager'
]

