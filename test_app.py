"""
Test application for flask-headless-payments
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os
import sys

# Add package to path
sys.path.insert(0, os.path.dirname(__file__))

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = 'test-secret-key'
app.config['JWT_SECRET_KEY'] = 'test-jwt-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Stripe configuration (test mode)
app.config['STRIPE_API_KEY'] = os.getenv('STRIPE_API_KEY', 'sk_test_dummy_key')
app.config['STRIPE_WEBHOOK_SECRET'] = os.getenv('STRIPE_WEBHOOK_SECRET', 'whsec_dummy')

# Initialize database
db = SQLAlchemy(app)

# Create User model with SubscriptionMixin
from flask_headless_payments import SubscriptionMixin

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(1024))
    
    # Add SubscriptionMixin fields
    stripe_customer_id = db.Column(db.String(255), unique=True)
    stripe_subscription_id = db.Column(db.String(255))
    plan_name = db.Column(db.String(50))
    plan_status = db.Column(db.String(50))
    current_period_start = db.Column(db.DateTime)
    current_period_end = db.Column(db.DateTime)
    trial_start = db.Column(db.DateTime)
    trial_end = db.Column(db.DateTime)
    cancel_at_period_end = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=db.func.now())

# Add mixin methods
for attr_name in dir(SubscriptionMixin):
    if not attr_name.startswith('_') and callable(getattr(SubscriptionMixin, attr_name)):
        if not hasattr(User, attr_name):
            setattr(User, attr_name, getattr(SubscriptionMixin, attr_name))

# Initialize JWT
from flask_jwt_extended import JWTManager, create_access_token
jwt = JWTManager(app)

# Initialize PaymentSvc
from flask_headless_payments import PaymentSvc

plans = {
    'free': {
        'name': 'Free',
        'price_id': None,
        'features': ['basic_pdf'],
        'limits': {'conversions': 10}
    },
    'pro': {
        'name': 'Pro',  
        'price_id': 'price_test_pro',
        'features': ['basic_pdf', 'advanced_pdf'],
        'limits': {'conversions': 100}
    },
    'enterprise': {
        'name': 'Enterprise',
        'price_id': 'price_test_enterprise',
        'features': ['basic_pdf', 'advanced_pdf', 'api_access'],
        'limits': {'conversions': -1}
    }
}

payments = PaymentSvc(app, user_model=User, plans=plans)

# Create tables
with app.app_context():
    db.create_all()
    
    # Create a test user if doesn't exist
    test_user = User.query.filter_by(email='test@example.com').first()
    if not test_user:
        test_user = User(email='test@example.com', password_hash='dummy')
        db.session.add(test_user)
        db.session.commit()
        print(f"Created test user with ID: {test_user.id}")

# Test routes
@app.route('/')
def index():
    return {
        'message': 'Flask-Headless-Payments Test Server',
        'version': '0.1.0',
        'endpoints': {
            'health': '/health',
            'plans': '/api/payments/plans',
            'auth': '/test/login',
            'docs': 'See README.md'
        }
    }

@app.route('/test/login', methods=['POST'])
def test_login():
    """Create a test JWT token"""
    user = User.query.filter_by(email='test@example.com').first()
    if user:
        access_token = create_access_token(identity=user.id)
        return {
            'access_token': access_token,
            'user_id': user.id,
            'email': user.email
        }
    return {'error': 'User not found'}, 404

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 Flask-Headless-Payments Test Server")
    print("="*60)
    print("\nAvailable Endpoints:")
    print("  GET  /                          - API info")
    print("  GET  /health                    - Health check")
    print("  GET  /api/payments/plans        - List plans")
    print("  POST /test/login                - Get test JWT token")
    print("  GET  /api/payments/subscription - Get subscription (auth required)")
    print("  POST /api/payments/checkout     - Create checkout (auth required)")
    print("  POST /api/payments/portal       - Customer portal (auth required)")
    print("\nTest User:")
    print("  Email: test@example.com")
    print("  Use /test/login to get JWT token")
    print("\n" + "="*60 + "\n")
    
    app.run(host='0.0.0.0', port=5001, debug=True)

