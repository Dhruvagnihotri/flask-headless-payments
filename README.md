# Flask-Headless-Payments

**Modern, headless payment integration for Flask APIs. Stripe subscriptions + webhooks + plan management in one line.**

[![PyPI version](https://badge.fury.io/py/flask-headless-payments.svg)](https://badge.fury.io/py/flask-headless-payments)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ Features

- ✅ **Drop-in Integration** - Add payments to any Flask app in minutes
- ✅ **Stripe Checkout** - Pre-built checkout sessions with trial support
- ✅ **Subscription Management** - Upgrade, downgrade, cancel subscriptions
- ✅ **Customer Portal** - Self-service billing management
- ✅ **Webhook Handling** - Automatic event processing with extensibility
- ✅ **Plan-Based Access Control** - Decorators to protect routes by plan
- ✅ **Usage Tracking** - Built-in metered billing support
- ✅ **Headless Architecture** - Perfect for SPAs, mobile apps, and APIs
- ✅ **Works with flask-headless-auth** - Seamless integration with authentication

## 🚀 Quick Start

### Installation

```bash
pip install flask-headless-payments
```

### Basic Setup (5 minutes)

```python
from flask import Flask
from flask_headless_auth import AuthSvc
from flask_headless_payments import PaymentSvc

app = Flask(__name__)

# Configure
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['JWT_SECRET_KEY'] = 'your-jwt-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'

# Stripe configuration
app.config['STRIPE_API_KEY'] = 'sk_test_...'
app.config['STRIPE_WEBHOOK_SECRET'] = 'whsec_...'

# Initialize auth (required)
auth = AuthSvc(app)

# Initialize payments
payments = PaymentSvc(
    app,
    plans={
        'free': {
            'name': 'Free',
            'price_id': None,
            'features': ['basic_features'],
            'limits': {'api_calls': 100}
        },
        'pro': {
            'name': 'Pro',
            'price_id': 'price_1234567890',  # From Stripe Dashboard
            'features': ['basic_features', 'advanced_features'],
            'limits': {'api_calls': 1000}
        },
        'enterprise': {
            'name': 'Enterprise',
            'price_id': 'price_0987654321',
            'features': ['basic_features', 'advanced_features', 'premium_features'],
            'limits': {'api_calls': 10000}
        }
    }
)

if __name__ == '__main__':
    app.run()
```

Your API now has payment endpoints ready at `/api/payments/*` 🎉

## 📚 API Endpoints

All endpoints are automatically registered:

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/payments/plans` | GET | No | Get all available plans |
| `/api/payments/subscription` | GET | Yes | Get current user's subscription |
| `/api/payments/checkout` | POST | Yes | Create checkout session |
| `/api/payments/portal` | POST | Yes | Create customer portal session |
| `/api/payments/cancel` | POST | Yes | Cancel subscription |
| `/api/payments/upgrade` | POST | Yes | Upgrade/downgrade plan |
| `/api/payments/webhook` | POST | No | Stripe webhook handler |

## 🎯 Usage Examples

### 1. Protect Routes by Plan

```python
from flask_jwt_extended import jwt_required
from flask_headless_payments import requires_plan

@app.route('/api/premium-feature')
@jwt_required()
@requires_plan('pro', 'enterprise')
def premium_feature():
    return {'message': 'Premium content'}
```

### 2. Require Any Active Subscription

```python
from flask_headless_payments import requires_active_subscription

@app.route('/api/subscriber-only')
@jwt_required()
@requires_active_subscription
def subscriber_feature():
    return {'message': 'Subscriber content'}
```

### 3. Check for Specific Features

```python
from flask_headless_payments import requires_feature

@app.route('/api/advanced-feature')
@jwt_required()
@requires_feature('advanced_features')
def advanced_feature():
    return {'message': 'Advanced feature'}
```

### 4. Track Usage (Metered Billing)

```python
from flask_headless_payments import track_usage

@app.route('/api/convert-pdf')
@jwt_required()
@track_usage('pdf_conversion', quantity=1)
def convert_pdf():
    return {'message': 'PDF converted'}
```

## 🔧 Configuration

### Required Settings

```python
# Stripe credentials
app.config['STRIPE_API_KEY'] = 'sk_test_...'
app.config['STRIPE_WEBHOOK_SECRET'] = 'whsec_...'
```

### Optional Settings

```python
# URL prefix for payment routes (default: '/api/payments')
app.config['PAYMENTSVC_URL_PREFIX'] = '/api/payments'

# Frontend URLs for redirects
app.config['PAYMENTSVC_SUCCESS_URL'] = 'http://localhost:3000/success'
app.config['PAYMENTSVC_CANCEL_URL'] = 'http://localhost:3000/cancel'
app.config['PAYMENTSVC_RETURN_URL'] = 'http://localhost:3000/account'

# Default trial period (days)
app.config['PAYMENTSVC_DEFAULT_TRIAL_DAYS'] = 14

# Default currency
app.config['PAYMENTSVC_DEFAULT_CURRENCY'] = 'usd'

# Feature flags
app.config['PAYMENTSVC_ENABLE_TRIALS'] = True
app.config['PAYMENTSVC_ENABLE_USAGE_TRACKING'] = True

# CORS origins
app.config['PAYMENTSVC_CORS_ORIGINS'] = ['http://localhost:3000']
```

## 💡 Frontend Integration

### Create Checkout Session

```javascript
// JavaScript/React example
async function subscribe(planName) {
  const response = await fetch('/api/payments/checkout', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${accessToken}`
    },
    body: JSON.stringify({ plan: planName })
  });
  
  const { url } = await response.json();
  window.location.href = url;  // Redirect to Stripe Checkout
}
```

### Open Customer Portal

```javascript
async function manageBilling() {
  const response = await fetch('/api/payments/portal', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  });
  
  const { url } = await response.json();
  window.location.href = url;  // Redirect to Stripe Portal
}
```

### Get Current Subscription

```javascript
async function getSubscription() {
  const response = await fetch('/api/payments/subscription', {
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  });
  
  const { subscription } = await response.json();
  console.log(subscription);
  // {
  //   plan_name: 'pro',
  //   plan_status: 'active',
  //   is_subscribed: true,
  //   days_until_renewal: 25,
  //   ...
  // }
}
```

## 🔌 Advanced: Custom Models

### Extend Your User Model

```python
from flask_sqlalchemy import SQLAlchemy
from flask_headless_payments import SubscriptionMixin

db = SQLAlchemy()

class User(db.Model, SubscriptionMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(1024))
    
    # SubscriptionMixin adds:
    # - stripe_customer_id
    # - stripe_subscription_id
    # - plan_name, plan_status
    # - current_period_start, current_period_end
    # - trial_start, trial_end
    # - is_subscribed(), has_plan(), etc.

# Initialize with custom model
payments = PaymentSvc(app, user_model=User, plans={...})
```

## 🪝 Webhooks

### Setting Up Webhooks

1. **In Stripe Dashboard:**
   - Go to Developers → Webhooks
   - Add endpoint: `https://yourdomain.com/api/payments/webhook`
   - Select events to listen to (or select all)
   - Copy the webhook signing secret

2. **In Your App:**
   ```python
   app.config['STRIPE_WEBHOOK_SECRET'] = 'whsec_...'
   ```

3. **Test Locally with Stripe CLI:**
   ```bash
   stripe listen --forward-to localhost:5000/api/payments/webhook
   ```

### Custom Webhook Handlers

```python
def custom_invoice_handler(event_data, db, user_model):
    """Custom handler for invoice.paid events."""
    invoice_id = event_data['id']
    customer_id = event_data['customer']
    
    # Your custom logic
    print(f"Invoice {invoice_id} paid by {customer_id}")

# Register custom handler
payments.register_webhook_handler('invoice.paid', custom_invoice_handler)
```

## 🎨 Plan Configuration

### Define Your Plans

```python
plans = {
    'free': {
        'name': 'Free',
        'price_id': None,  # Free tier has no Stripe price
        'features': ['basic_pdf', 'compress'],
        'limits': {
            'pdf_conversions': 10,
            'storage_mb': 100
        }
    },
    'pro': {
        'name': 'Pro',
        'price_id': 'price_1234567890',  # Monthly price from Stripe
        'features': ['basic_pdf', 'compress', 'merge', 'split'],
        'limits': {
            'pdf_conversions': 100,
            'storage_mb': 1000
        }
    },
    'enterprise': {
        'name': 'Enterprise',
        'price_id': 'price_0987654321',
        'features': ['basic_pdf', 'compress', 'merge', 'split', 'api_access', 'priority_support'],
        'limits': {
            'pdf_conversions': -1,  # Unlimited
            'storage_mb': -1
        }
    }
}

payments = PaymentSvc(app, plans=plans)
```

### Check Features in Code

```python
from flask import current_app

@app.route('/api/check-limit')
@jwt_required()
def check_limit():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    payment_svc = current_app.extensions['paymentsvc']
    limit = payment_svc.plan_manager.get_plan_limit(user.plan_name, 'pdf_conversions')
    
    return {'limit': limit}
```

## 🔒 Security Best Practices

1. **Always use HTTPS in production**
2. **Keep your Stripe keys secure** (use environment variables)
3. **Verify webhook signatures** (handled automatically)
4. **Use JWT authentication** with flask-headless-auth
5. **Validate plan changes** server-side

## 🤝 Integration with flask-headless-auth

Flask-Headless-Payments is designed to work seamlessly with flask-headless-auth:

```python
from flask_headless_auth import AuthSvc
from flask_headless_payments import PaymentSvc

# Initialize auth first
auth = AuthSvc(app)

# Payments automatically detects and uses auth's User model
payments = PaymentSvc(app, plans={...})

# Now protect routes with both auth AND plan requirements
@app.route('/api/premium')
@jwt_required()
@requires_plan('pro')
def premium():
    return {'message': 'Premium feature'}
```

## 📦 What's Included

### Models (with Mixins)
- `Customer` - Stripe customer data
- `Payment` - Payment transaction records
- `WebhookEvent` - Webhook event log
- `UsageRecord` - Metered billing usage

### Managers
- `SubscriptionManager` - Subscription CRUD operations
- `CheckoutManager` - Checkout & portal sessions
- `WebhookManager` - Webhook event processing
- `PlanManager` - Plan configuration & access control

### Decorators
- `@requires_plan()` - Require specific plan(s)
- `@requires_active_subscription` - Require any active subscription
- `@requires_feature()` - Require specific feature
- `@track_usage()` - Track usage for metered billing

## 🎓 Examples

Check out the `examples/` directory for complete working examples:

- **Basic SaaS** - Simple subscription app
- **With flask-headless-auth** - Full auth + payments
- **Metered Billing** - Usage-based pricing
- **Custom Webhooks** - Advanced webhook handling

## 🐛 Troubleshooting

### Issue: "User model does not support subscriptions"

**Solution:** Add `SubscriptionMixin` to your User model:
```python
from flask_headless_payments import SubscriptionMixin

class User(db.Model, SubscriptionMixin):
    # ... your fields
```

### Issue: "STRIPE_WEBHOOK_SECRET not configured"

**Solution:** Set the webhook secret in your config:
```python
app.config['STRIPE_WEBHOOK_SECRET'] = 'whsec_...'
```

Get it from: Stripe Dashboard → Developers → Webhooks

### Issue: "No active subscription found"

**Solution:** Ensure user has completed checkout and webhook has been processed.

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details.

## 🙏 Credits

Developed with ❤️ by [Dhruv Agnihotri](https://github.com/Dhruvagnihotri)

Built with Flask, Stripe Python SDK, and Flask-SQLAlchemy.

Companion to [flask-headless-auth](https://github.com/Dhruvagnihotri/flask-headless-auth).

---

**Made for modern SaaS applications. Deploy with confidence.** 💳
