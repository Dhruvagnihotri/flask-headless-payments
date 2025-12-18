# Flask-Headless-Payments Architecture

## 📐 Design Overview

Flask-Headless-Payments follows the exact same pattern as flask-headless-auth, providing a drop-in, reusable payment integration for Flask applications.

## 🏗️ Core Architecture

```
flask_headless_payments/
├── __init__.py              # Main exports (PaymentSvc, decorators, mixins)
├── __version__.py           # Version information
├── core.py                  # PaymentSvc - Main extension class
├── config.py                # Default configuration
├── extensions.py            # Flask extension singletons (db)
├── models.py                # Default model implementations
├── decorators.py            # Plan protection decorators
│
├── mixins/                  # Reusable model mixins
│   ├── subscription.py      # SubscriptionMixin for User model
│   ├── customer.py          # CustomerMixin
│   ├── payment.py           # PaymentMixin
│   └── webhook.py           # WebhookEventMixin
│
├── managers/                # Business logic layer
│   ├── subscription_manager.py  # Subscription CRUD with Stripe
│   ├── checkout_manager.py      # Checkout & portal sessions
│   ├── webhook_manager.py       # Webhook event processing
│   └── plan_manager.py          # Plan configuration & access control
│
└── routes/                  # API endpoints
    └── payments.py          # Payment routes blueprint
```

## 🎯 Design Principles

### 1. **80/20 Rule - Reusability**

**80% Reusable (Handled by the library):**
- ✅ Stripe API integration
- ✅ Customer creation and management
- ✅ Subscription lifecycle (create, update, cancel)
- ✅ Webhook signature verification
- ✅ Webhook event processing
- ✅ Checkout session creation
- ✅ Customer portal access
- ✅ Database models and migrations
- ✅ API routes and error handling

**20% Customizable (User's business logic):**
- 🔧 Plan definitions (features, pricing)
- 🔧 Trial period configuration
- 🔧 Success/cancel URLs
- 🔧 Custom webhook handlers
- 🔧 Custom features and limits
- 🔧 Email notifications (optional)

### 2. **Separation of Concerns**

```
User Request → Routes → Managers → Stripe API
                ↓         ↓
              Models ← Database
```

- **Routes**: HTTP interface, validation, auth
- **Managers**: Business logic, Stripe operations
- **Models**: Data persistence
- **Mixins**: Reusable model behaviors

### 3. **Progressive Enhancement**

Users can start simple and add complexity as needed:

**Level 1: Basic Integration**
```python
payments = PaymentSvc(app, plans={'free': {...}, 'pro': {...}})
```

**Level 2: Custom Models**
```python
class User(db.Model, SubscriptionMixin):
    # Your custom fields
    pass

payments = PaymentSvc(app, user_model=User, plans={...})
```

**Level 3: Custom Webhooks**
```python
def my_handler(event_data, db, user_model):
    # Custom logic
    pass

payments.register_webhook_handler('invoice.paid', my_handler)
```

## 🔄 Key Flows

### Subscription Flow

```
1. User clicks "Subscribe" in frontend
   ↓
2. Frontend calls POST /api/payments/checkout
   ↓
3. Backend creates Stripe Checkout session
   ↓
4. Frontend redirects to Stripe hosted page
   ↓
5. User completes payment on Stripe
   ↓
6. Stripe sends webhook to /api/payments/webhook
   ↓
7. Backend processes webhook, updates user subscription
   ↓
8. User redirected to success page
```

### Webhook Flow

```
1. Stripe event occurs (payment, subscription update, etc.)
   ↓
2. Stripe sends webhook to /api/payments/webhook
   ↓
3. WebhookManager verifies signature
   ↓
4. Event saved to database (WebhookEvent table)
   ↓
5. WebhookManager processes event:
   - Check for custom handler
   - If not, use default handler
   ↓
6. Update user subscription status in database
   ↓
7. Mark webhook as processed
```

### Plan Protection Flow

```
1. Request to protected route
   ↓
2. @jwt_required() validates JWT token
   ↓
3. @requires_plan('pro') checks:
   - User exists?
   - Has active subscription?
   - Subscription plan matches?
   ↓
4. If yes: Allow request
   If no: Return 403 with details
```

## 🧩 Component Details

### PaymentSvc (core.py)

Main extension class that orchestrates everything:
- Initializes database and models
- Creates manager instances
- Registers routes
- Configures Stripe

**Key Methods:**
- `init_app()` - Initialize with Flask app
- `register_webhook_handler()` - Add custom webhook handlers

### Managers

**SubscriptionManager:**
- `get_or_create_customer()` - Stripe customer management
- `create_subscription()` - Create new subscription
- `update_user_subscription()` - Sync Stripe → Database
- `cancel_subscription()` - Cancel subscription
- `update_subscription()` - Change plan

**CheckoutManager:**
- `create_checkout_session()` - Stripe Checkout
- `create_portal_session()` - Customer Portal
- `retrieve_session()` - Get session details

**WebhookManager:**
- `verify_webhook()` - Signature verification
- `process_event()` - Event processing
- `register_handler()` - Custom handlers
- `_handle_*()` - Default event handlers

**PlanManager:**
- `get_plan()` - Plan configuration
- `has_feature()` - Feature checking
- `get_plan_limit()` - Limit retrieval
- `compare_plans()` - Plan hierarchy

### Models & Mixins

**SubscriptionMixin (for User model):**
```python
Fields:
- stripe_customer_id
- stripe_subscription_id
- plan_name, plan_status
- current_period_start, current_period_end
- trial_start, trial_end

Methods:
- is_subscribed()
- is_on_trial()
- has_plan()
- subscription_active()
- days_until_renewal()
```

**Default Models:**
- `Customer` - Stripe customer data
- `Payment` - Payment records
- `WebhookEvent` - Webhook log
- `UsageRecord` - Metered billing

### Routes (payments.py)

All routes automatically registered at `/api/payments`:

| Route | Method | Description |
|-------|--------|-------------|
| `/plans` | GET | List plans |
| `/subscription` | GET | Current subscription |
| `/checkout` | POST | Create checkout |
| `/portal` | POST | Open portal |
| `/cancel` | POST | Cancel subscription |
| `/upgrade` | POST | Change plan |
| `/webhook` | POST | Webhook handler |

### Decorators (decorators.py)

**@requires_plan('pro', 'enterprise')**
- Checks if user has one of specified plans
- Returns 403 if not subscribed or wrong plan

**@requires_active_subscription**
- Checks if user has any active subscription
- Returns 403 if not subscribed

**@requires_feature('advanced_editing')**
- Checks if user's plan includes feature
- Returns 403 if feature not available

**@track_usage('pdf_conversion')**
- Tracks usage for metered billing
- Non-blocking (logs errors, doesn't fail request)

## 🔌 Integration Points

### With flask-headless-auth

```python
# PaymentSvc automatically detects auth's User model
auth = AuthSvc(app)
payments = PaymentSvc(app, plans={...})  # Uses auth.user_model

# Decorators work together
@jwt_required()           # From flask-headless-auth
@requires_plan('pro')     # From flask-headless-payments
def premium():
    pass
```

### With Custom User Models

```python
class User(db.Model, UserMixin, SubscriptionMixin):
    # Your fields
    pass

# Both mixins work together
auth = AuthSvc(app, user_model=User)
payments = PaymentSvc(app, plans={...})  # Auto-detects User model
```

## 🛡️ Security

### Webhook Verification
- Stripe signature verification (SHA-256 HMAC)
- Prevents unauthorized webhook calls
- 5-minute tolerance window

### JWT Protection
- All subscription endpoints require JWT
- Uses flask-jwt-extended for token validation
- Returns 401 if token missing/invalid

### Plan Protection
- Server-side validation only
- Cannot be bypassed by frontend
- Detailed error responses for debugging

## 📊 Database Schema

```sql
-- User table (from flask-headless-auth + SubscriptionMixin)
users
├── id (PK)
├── email
├── password_hash
├── stripe_customer_id (unique)
├── stripe_subscription_id
├── plan_name
├── plan_status
├── current_period_start
├── current_period_end
└── trial_end

-- Customer table
paymentsvc_customers
├── id (PK)
├── stripe_customer_id (unique)
├── user_id
├── email
└── payment_method_id

-- Payment table
paymentsvc_payments
├── id (PK)
├── stripe_payment_intent_id
├── user_id
├── amount
├── status
└── created_at

-- WebhookEvent table
paymentsvc_webhook_events
├── id (PK)
├── stripe_event_id (unique)
├── event_type
├── data (JSON)
├── processed
└── received_at
```

## 🎨 Extensibility

### Custom Models

Replace any default model:
```python
class CustomPayment(db.Model, PaymentMixin):
    # Your custom fields
    pass

payments = PaymentSvc(app, payment_model=CustomPayment, plans={...})
```

### Custom Webhooks

Add custom event handlers:
```python
def handle_refund(event_data, db, user_model):
    # Your logic
    pass

payments.register_webhook_handler('charge.refunded', handle_refund)
```

### Custom Features

Define in plan configuration:
```python
plans = {
    'pro': {
        'features': ['custom_feature_1', 'custom_feature_2'],
        'limits': {'custom_limit': 100}
    }
}
```

Then check in code:
```python
@requires_feature('custom_feature_1')
def custom_route():
    pass
```

## 🚀 Performance

### Database Queries
- Indexed fields: `stripe_customer_id`, `stripe_subscription_id`, `user_id`
- Efficient lookups by customer/subscription ID

### Webhook Processing
- Events saved immediately
- Processed asynchronously (can be moved to background worker)
- Retry logic for failed processing

### Caching (Future)
- Plan configurations can be cached
- User subscription status can be cached
- Cache invalidation on webhook events

## 📈 Future Enhancements

1. **Metered Billing**: Full usage tracking and reporting
2. **Coupon Support**: Promo codes and discounts
3. **Multi-Currency**: Support for multiple currencies
4. **Team Subscriptions**: Organization-level subscriptions
5. **Usage Reports**: Analytics and reporting
6. **Email Notifications**: Subscription updates, receipts
7. **Payment Methods**: Support for multiple payment methods
8. **Invoicing**: Custom invoice generation

## 💡 Design Decisions

### Why Mixins?
- **Flexibility**: Users can combine with their own models
- **Non-invasive**: Doesn't force model structure
- **Composable**: Mix with other mixins (UserMixin, etc.)

### Why Managers?
- **Testability**: Easy to mock and test
- **Reusability**: Can be used outside routes
- **Single Responsibility**: Each manager has clear purpose

### Why Separate from flask-headless-auth?
- **Optional**: Not everyone needs payments
- **Size**: Keeps both packages focused
- **Dependencies**: Stripe is a big dependency
- **Versioning**: Independent release cycles

---

**Built with Flask best practices and modern design patterns.** 🏗️

