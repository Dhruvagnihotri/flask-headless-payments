# Quick Start Example

## Complete Working Example

```python
# app.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_headless_auth import AuthSvc
from flask_headless_payments import PaymentSvc, requires_plan
from flask_jwt_extended import jwt_required
import os

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'dev-jwt-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Stripe Configuration
app.config['STRIPE_API_KEY'] = os.getenv('STRIPE_API_KEY')
app.config['STRIPE_WEBHOOK_SECRET'] = os.getenv('STRIPE_WEBHOOK_SECRET')

# Frontend URLs
app.config['PAYMENTSVC_SUCCESS_URL'] = 'http://localhost:3000/success'
app.config['PAYMENTSVC_CANCEL_URL'] = 'http://localhost:3000/cancel'

# Initialize authentication
auth = AuthSvc(app)

# Initialize payments with plan configuration
payments = PaymentSvc(
    app,
    plans={
        'free': {
            'name': 'Free',
            'price_id': None,
            'features': ['basic_pdf'],
            'limits': {'conversions': 10}
        },
        'pro': {
            'name': 'Pro',
            'price_id': os.getenv('STRIPE_PRO_PRICE_ID'),
            'features': ['basic_pdf', 'advanced_pdf', 'api_access'],
            'limits': {'conversions': 100}
        },
        'enterprise': {
            'name': 'Enterprise',
            'price_id': os.getenv('STRIPE_ENTERPRISE_PRICE_ID'),
            'features': ['basic_pdf', 'advanced_pdf', 'api_access', 'priority_support'],
            'limits': {'conversions': -1}  # Unlimited
        }
    }
)

# Your app routes
@app.route('/')
def index():
    return {'message': 'Welcome to the API'}

@app.route('/api/free-feature')
def free_feature():
    return {'message': 'This is free for everyone'}

@app.route('/api/basic-feature')
@jwt_required()
def basic_feature():
    return {'message': 'This requires authentication'}

@app.route('/api/pro-feature')
@jwt_required()
@requires_plan('pro', 'enterprise')
def pro_feature():
    return {'message': 'This requires Pro or Enterprise plan'}

@app.route('/api/enterprise-feature')
@jwt_required()
@requires_plan('enterprise')
def enterprise_feature():
    return {'message': 'This requires Enterprise plan'}

if __name__ == '__main__':
    with app.app_context():
        # Create database tables
        from flask_headless_payments import db
        db.create_all()
    
    app.run(debug=True)
```

## Environment Variables (.env)

```bash
# Flask
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-here

# Stripe
STRIPE_API_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRO_PRICE_ID=price_...
STRIPE_ENTERPRISE_PRICE_ID=price_...
```

## Frontend Example (React)

```jsx
// SubscriptionButton.jsx
import { useState } from 'react';

function SubscriptionButton({ plan }) {
  const [loading, setLoading] = useState(false);
  
  const handleSubscribe = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/payments/checkout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({ plan })
      });
      
      const { url } = await response.json();
      window.location.href = url;
    } catch (error) {
      console.error('Error:', error);
      setLoading(false);
    }
  };
  
  return (
    <button onClick={handleSubscribe} disabled={loading}>
      {loading ? 'Loading...' : `Subscribe to ${plan}`}
    </button>
  );
}

export default SubscriptionButton;
```

## Testing the Setup

1. **Start the Flask app:**
   ```bash
   python app.py
   ```

2. **Register a user:**
   ```bash
   curl -X POST http://localhost:5000/api/auth/register \
     -H "Content-Type: application/json" \
     -d '{"email": "test@example.com", "password": "password123"}'
   ```

3. **Login:**
   ```bash
   curl -X POST http://localhost:5000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email": "test@example.com", "password": "password123"}'
   ```

4. **Get available plans:**
   ```bash
   curl http://localhost:5000/api/payments/plans
   ```

5. **Create checkout session:**
   ```bash
   curl -X POST http://localhost:5000/api/payments/checkout \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
     -d '{"plan": "pro"}'
   ```

6. **Test webhook locally:**
   ```bash
   stripe listen --forward-to localhost:5000/api/payments/webhook
   ```

That's it! You now have a complete payment-enabled Flask API. 🎉

