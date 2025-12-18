# 🔌 Extensibility Guide - Flask-Headless-Payments

## Overview

Flask-Headless-Payments is built with **extensibility as a core principle**. You can customize behavior without modifying library code.

## 🎯 Extension Mechanisms

### 1. **Hooks** - Modify Behavior
Hooks let you inject custom logic at specific points.

### 2. **Events** - React to Changes  
Events notify your code when something happens.

### 3. **Plugins** - Package Extensions
Plugins bundle hooks and events into reusable modules.

---

## 📚 Complete Extension Guide

### Method 1: Hooks (Synchronous)

**Use when:** You need to modify or validate data before/after operations.

```python
from flask_headless_payments.extensibility import hook

# Validate before creating subscription
@hook('before_subscription_create', priority=10)
def validate_subscription(customer_id, price_id, **kwargs):
    # Custom validation
    if not is_valid_price(price_id):
        raise ValueError("Invalid price ID")
    
    # Log for audit
    logger.info(f"Creating subscription for {customer_id}")

# Send notification after subscription created
@hook('after_subscription_create')
def notify_team(subscription_id, customer_id, **kwargs):
    send_slack_notification(f"New subscription: {subscription_id}")

# Handle failures
@hook('subscription_create_failed')
def log_failure(customer_id, error, **kwargs):
    logger.error(f"Subscription failed for {customer_id}: {error}")
```

**Available Hooks:**
```python
# Customer hooks
'before_customer_create'
'after_customer_create'
'customer_create_failed'

# Subscription hooks
'before_subscription_create'
'after_subscription_create'
'subscription_create_failed'
'before_subscription_update'
'after_subscription_update'
'before_subscription_cancel'
'after_subscription_cancel'

# Webhook hooks
'before_webhook_process'
'after_webhook_process'
'webhook_process_failed'

# Payment hooks
'payment_succeeded'
'payment_failed'

# General hooks
'before_stripe_api_call'
'after_stripe_api_call'
'stripe_api_error'
```

---

### Method 2: Events (Asynchronous)

**Use when:** You need to react to changes without blocking the main flow.

```python
from flask_headless_payments.extensibility import event

# Send welcome email
@event('subscription.created')
def send_welcome_email(evt):
    user_id = evt.data['user_id']
    subscription_id = evt.data['subscription_id']
    
    # Send email (non-blocking)
    send_email_async(user_id, 'Welcome to Pro!')

# Track analytics
@event('subscription.created')
def track_analytics(evt):
    analytics.track('subscription_created', {
        'user_id': evt.data['user_id'],
        'plan': evt.data.get('price_id')
    })

# Update CRM
@event('subscription.cancelled')
def update_crm(evt):
    crm.update_subscription_status(
        evt.data['subscription_id'],
        'cancelled'
    )
```

**Available Events:**
```python
# Customer events
'customer.created'
'customer.updated'

# Subscription events
'subscription.created'
'subscription.updated'
'subscription.cancelled'
'subscription.renewed'
'subscription.expired'

# Payment events
'payment.succeeded'
'payment.failed'
'payment.refunded'

# Webhook events
'webhook.received'
'webhook.processed'
'webhook.failed'

# Plan events
'plan.upgraded'
'plan.downgraded'

# Error events
'error.stripe_api'
'error.database'
```

---

### Method 3: Plugins (Packaged Extensions)

**Use when:** You want to bundle multiple hooks/events into a reusable module.

```python
from flask_headless_payments.extensibility import Plugin

class EmailNotificationPlugin(Plugin):
    """Send email notifications for subscription events."""
    
    name = 'email_notifications'
    version = '1.0.0'
    description = 'Sends email notifications'
    author = 'Your Name'
    
    def on_load(self, payment_svc):
        """Called when plugin loads."""
        self.payment_svc = payment_svc
        
        # Register hooks
        payment_svc.hook_manager.register('after_subscription_create')(
            self.send_welcome_email
        )
        
        # Subscribe to events
        from flask_headless_payments.extensibility import get_event_manager
        event_manager = get_event_manager()
        event_manager.subscribe('subscription.cancelled')(
            self.send_cancellation_email
        )
    
    def on_unload(self):
        """Called when plugin unloads."""
        logger.info("Email plugin unloaded")
    
    def send_welcome_email(self, **kwargs):
        user_id = kwargs.get('user_id')
        # Send welcome email
        send_email(user_id, 'Welcome!')
    
    def send_cancellation_email(self, event):
        user_id = event.data['user_id']
        # Send cancellation email
        send_email(user_id, 'Sorry to see you go')

# Usage:
payments = PaymentSvc(app, plans={...})
payments.plugin_manager.register(EmailNotificationPlugin())
payments.plugin_manager.load_all()
```

---

## 🎨 Real-World Examples

### Example 1: Custom Validation

```python
from flask_headless_payments.extensibility import hook

@hook('before_subscription_create', priority=5)
def check_user_eligibility(customer_id, price_id, **kwargs):
    """Ensure user meets requirements for this plan."""
    user = User.query.filter_by(stripe_customer_id=customer_id).first()
    
    if price_id == 'price_enterprise' and not user.company_verified:
        raise ValueError("Enterprise plan requires company verification")
    
    if user.has_outstanding_balance():
        raise ValueError("Cannot subscribe with outstanding balance")
```

### Example 2: Analytics Tracking

```python
from flask_headless_payments.extensibility import event

@event('subscription.created')
def track_conversion(evt):
    """Track subscription conversion in analytics."""
    analytics.track('subscription_started', {
        'user_id': evt.data['user_id'],
        'plan': evt.data['price_id'],
        'trial': evt.data.get('trial_days', 0) > 0,
        'timestamp': evt.timestamp
    })

@event('subscription.cancelled')
def track_churn(evt):
    """Track subscription cancellation."""
    analytics.track('subscription_churned', {
        'subscription_id': evt.data['subscription_id'],
        'timestamp': evt.timestamp
    })
```

### Example 3: Slack Notifications

```python
from flask_headless_payments.extensibility import Plugin

class SlackNotificationPlugin(Plugin):
    name = 'slack_notifications'
    version = '1.0.0'
    
    def __init__(self, webhook_url):
        super().__init__()
        self.webhook_url = webhook_url
    
    def on_load(self, payment_svc):
        from flask_headless_payments.extensibility import get_event_manager
        event_manager = get_event_manager()
        
        event_manager.subscribe('subscription.created')(self.notify_new_subscription)
        event_manager.subscribe('payment.failed')(self.notify_payment_failure)
    
    def notify_new_subscription(self, event):
        self._send_slack({
            'text': f"🎉 New subscription: {event.data['subscription_id']}"
        })
    
    def notify_payment_failure(self, event):
        self._send_slack({
            'text': f"⚠️ Payment failed: {event.data['subscription_id']}"
        })
    
    def _send_slack(self, data):
        requests.post(self.webhook_url, json=data)

# Usage:
slack = SlackNotificationPlugin(webhook_url='https://hooks.slack.com/...')
payments.plugin_manager.register(slack)
payments.plugin_manager.load('slack_notifications')
```

### Example 4: Custom Metrics

```python
from flask_headless_payments.extensibility import Plugin

class MetricsPlugin(Plugin):
    name = 'metrics'
    version = '1.0.0'
    
    def __init__(self):
        super().__init__()
        self.metrics = {
            'mrr': 0,  # Monthly Recurring Revenue
            'churn_rate': 0,
            'active_subscriptions': 0
        }
    
    def on_load(self, payment_svc):
        from flask_headless_payments.extensibility import get_event_manager
        event_manager = get_event_manager()
        
        event_manager.subscribe('subscription.created')(self.update_mrr)
        event_manager.subscribe('subscription.cancelled')(self.update_churn)
    
    def update_mrr(self, event):
        # Calculate MRR from subscription data
        self.metrics['mrr'] += self._calculate_mrr(event.data)
        self.metrics['active_subscriptions'] += 1
    
    def update_churn(self, event):
        self.metrics['active_subscriptions'] -= 1
        self.metrics['churn_rate'] = self._calculate_churn_rate()
    
    def _calculate_mrr(self, data):
        # Your MRR calculation logic
        return 29.99  # Example
    
    def _calculate_churn_rate(self):
        # Your churn calculation logic
        return 0.05  # Example

# Usage:
metrics = MetricsPlugin()
payments.plugin_manager.register(metrics)
payments.plugin_manager.load('metrics')

# Access metrics
@app.route('/api/admin/metrics')
def get_metrics():
    plugin = payments.plugin_manager.get_plugin('metrics')
    return jsonify(plugin.metrics)
```

---

## 🔧 Advanced Patterns

### Pattern 1: Conditional Hooks

```python
@hook('before_subscription_create')
def apply_discount(customer_id, price_id, **kwargs):
    """Apply discount for specific customers."""
    user = get_user_by_customer_id(customer_id)
    
    if user.is_early_adopter:
        # Modify the subscription creation
        kwargs['coupon'] = 'EARLYBIRD50'
```

### Pattern 2: Hook Priority

```python
# Lower priority runs first
@hook('before_subscription_create', priority=1)
def validate_first(**kwargs):
    # This runs before everything else
    pass

@hook('before_subscription_create', priority=50)
def normal_hook(**kwargs):
    # Default priority
    pass

@hook('before_subscription_create', priority=100)
def runs_last(**kwargs):
    # This runs last
    pass
```

### Pattern 3: Event History

```python
from flask_headless_payments.extensibility import get_event_manager

# Get recent events
event_manager = get_event_manager()
recent_events = event_manager.get_history(limit=100)

# Filter by type
subscription_events = event_manager.get_history(
    event_name='subscription.created',
    limit=50
)
```

---

## 📋 Best Practices

### 1. **Hooks Should Be Fast**
Don't do heavy processing in hooks - they block the main flow.

```python
# ❌ Bad - Blocks subscription creation
@hook('after_subscription_create')
def slow_hook(**kwargs):
    time.sleep(10)  # Don't do this!
    heavy_computation()

# ✅ Good - Offload to background
@hook('after_subscription_create')
def fast_hook(**kwargs):
    queue.enqueue(heavy_computation, kwargs)
```

### 2. **Events Are Async-Friendly**
Use events for non-blocking operations.

```python
# ✅ Good - Non-blocking
@event('subscription.created')
def send_emails(evt):
    # This won't block subscription creation
    send_welcome_email_async(evt.data['user_id'])
```

### 3. **Handle Errors Gracefully**
Don't let your hooks break the main flow.

```python
@hook('after_subscription_create')
def notify_external_system(**kwargs):
    try:
        external_api.notify(kwargs)
    except Exception as e:
        # Log but don't raise
        logger.error(f"External notification failed: {e}")
```

### 4. **Document Your Extensions**
Make it clear what your hooks/events do.

```python
@hook('before_subscription_create')
def validate_corporate_email(**kwargs):
    """
    Validates that enterprise subscriptions use corporate email.
    
    Raises ValueError if validation fails.
    """
    # Implementation
```

---

## 🎯 When to Use What

| Scenario | Use |
|----------|-----|
| Validate input before operation | **Hook** (before_*) |
| Send notifications | **Event** |
| Log for audit | **Hook** (after_*) or **Event** |
| Integrate with external system | **Event** |
| Modify behavior | **Hook** |
| Collect metrics | **Event** or **Plugin** |
| Package reusable logic | **Plugin** |
| Add custom business rules | **Hook** |

---

## 🚀 Getting Started

### Step 1: Choose Extension Type
- Need to modify behavior? → Hooks
- Need to react to changes? → Events
- Building reusable module? → Plugin

### Step 2: Register Your Extension
```python
from flask_headless_payments import PaymentSvc
from flask_headless_payments.extensibility import hook, event

# Register hooks
@hook('after_subscription_create')
def my_hook(**kwargs):
    pass

# Register events
@event('subscription.created')
def my_event(evt):
    pass

# Initialize
payments = PaymentSvc(app, plans={...})
```

### Step 3: Test
```python
# Trigger manually for testing
from flask_headless_payments.extensibility import get_hook_manager, get_event_manager

hook_manager = get_hook_manager()
hook_manager.trigger('after_subscription_create', user_id=1, subscription_id='sub_123')

event_manager = get_event_manager()
event_manager.publish('subscription.created', {'user_id': 1})
```

---

## 📚 More Examples

Check `examples/extensibility/` for complete working examples:
- Email notifications plugin
- Analytics tracking plugin
- Custom validation hooks
- Slack integration
- Metrics collection

---

**Now you can extend Flask-Headless-Payments without modifying library code!** 🎉

