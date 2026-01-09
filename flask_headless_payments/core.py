"""
flask_headless_payments.core
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Main PaymentSvc extension class.
"""

from flask import Flask
from typing import Optional, Dict, Any
import logging
import stripe

logger = logging.getLogger(__name__)


class PaymentSvc:
    """
    Main Flask-PaymentSvc extension.
    
    Usage:
        app = Flask(__name__)
        payments = PaymentSvc(app, plans={...})
        
    Or with app factory:
        payments = PaymentSvc()
        payments.init_app(app, plans={...})
    """
    
    def __init__(
        self,
        app: Optional[Flask] = None,
        user_model=None,
        customer_model=None,
        payment_model=None,
        webhook_event_model=None,
        usage_record_model=None,
        plans: Optional[Dict[str, Dict[str, Any]]] = None,
        blueprint_name: str = 'paymentsvc',
        url_prefix: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize the extension.
        
        Args:
            app: Flask application instance (optional)
            user_model: Custom User model (must include SubscriptionMixin)
            customer_model: Custom Customer model (optional)
            payment_model: Custom Payment model (optional)
            webhook_event_model: Custom WebhookEvent model (optional)
            usage_record_model: Custom UsageRecord model (optional)
            plans: Plan configuration dictionary
            blueprint_name: Unique name for the blueprint (default: 'paymentsvc')
            url_prefix: URL prefix for routes (default: from config or '/api/payments')
            webhook_secret: Stripe webhook secret for this instance (for monorepo support)
            **kwargs: Additional configuration options
        """
        self.app = None
        self.db = None
        
        # Store model classes
        self.user_model = user_model
        self.customer_model = customer_model
        self.payment_model = payment_model
        self.webhook_event_model = webhook_event_model
        self.usage_record_model = usage_record_model
        
        # Store plan configuration
        self.plans = plans or {}
        
        # Store blueprint configuration
        self.blueprint_name = blueprint_name
        self.url_prefix = url_prefix
        self.webhook_secret = webhook_secret
        
        # Managers
        self.subscription_manager = None
        self.checkout_manager = None
        self.webhook_manager = None
        self.plan_manager = None
        
        if app is not None:
            self.init_app(app, plans=plans, **kwargs)
    
    def init_app(self, app: Flask, plans: Optional[Dict[str, Dict[str, Any]]] = None, **kwargs):
        """
        Initialize the extension with Flask app.
        
        Args:
            app: Flask application instance
            plans: Plan configuration dictionary
            **kwargs: Additional configuration options
        """
        self.app = app
        self.config = app.config
        
        # Load default configuration
        self._load_config(app)
        
        # Validate required configuration
        self._validate_config(app)
        
        # Use provided plans or from kwargs
        if plans:
            self.plans = plans
        
        # Extract url_prefix, blueprint_name, and webhook_secret from kwargs if provided
        # This allows overriding via init_app for app factory pattern
        if 'url_prefix' in kwargs and not self.url_prefix:
            self.url_prefix = kwargs['url_prefix']
        if 'blueprint_name' in kwargs and self.blueprint_name == 'paymentsvc':
            self.blueprint_name = kwargs['blueprint_name']
        if 'webhook_secret' in kwargs and not self.webhook_secret:
            self.webhook_secret = kwargs['webhook_secret']
        
        # Initialize database
        self._init_database(app)
        
        # Initialize Stripe
        self._init_stripe(app)
        
        # Initialize managers
        self._init_managers(app)
        
        # Initialize CORS
        self._init_cors(app)
        
        # Register routes
        self._init_routes(app)
        
        # Store in app.extensions
        if not hasattr(app, 'extensions'):
            app.extensions = {}
        app.extensions['paymentsvc'] = self
        
        logger.info("Flask-PaymentSvc initialized successfully")
    
    def _load_config(self, app):
        """Load default configuration."""
        from flask_headless_payments.config import DEFAULT_CONFIG
        
        for key, value in DEFAULT_CONFIG.items():
            app.config.setdefault(key, value)
    
    def _validate_config(self, app):
        """Validate required configuration."""
        stripe_key = app.config.get('STRIPE_API_KEY')
        if not stripe_key:
            logger.warning("STRIPE_API_KEY not configured - payment functionality will not work")
        
        webhook_secret = (app.config.get(f'STRIPE_WEBHOOK_SECRET_{self.blueprint_name.upper()}') or 
                          app.config.get('STRIPE_WEBHOOK_SECRET'))
        if not webhook_secret:
            logger.warning("STRIPE_WEBHOOK_SECRET not configured - webhooks will not work")
    
    def _init_database(self, app):
        """Initialize database."""
        from flask_headless_payments import extensions
        
        # ALWAYS use existing db if available (priority order)
        if 'sqlalchemy' in app.extensions:
            logger.info("Using existing SQLAlchemy from app.extensions['sqlalchemy']")
            self.db = app.extensions['sqlalchemy']
            extensions.set_db(self.db)
        elif hasattr(app, 'db') and app.db:
            logger.info("Using existing SQLAlchemy from app.db")
            self.db = app.db
            extensions.set_db(self.db)
        else:
            logger.info("Creating new SQLAlchemy instance")
            self.db = extensions.get_db()
            self.db.init_app(app)
        
        # Create default models if custom ones not provided
        from flask_headless_payments.models import create_default_models
        (default_customer, default_payment, 
         default_webhook_event, default_usage_record, default_idempotency_key) = create_default_models(self.db)
        
        # Use custom models where provided, defaults otherwise
        self.customer_model = self.customer_model or default_customer
        self.payment_model = self.payment_model or default_payment
        self.webhook_event_model = self.webhook_event_model or default_webhook_event
        self.usage_record_model = self.usage_record_model or default_usage_record
        
        # User model must be provided or exist
        if not self.user_model:
            # Try to get from app extensions (flask-headless-auth)
            auth_svc = app.extensions.get('authsvc')
            if auth_svc and hasattr(auth_svc, 'user_model'):
                self.user_model = auth_svc.user_model
                logger.info("Using User model from flask-headless-auth")
            else:
                raise ValueError(
                    "user_model is required. Either provide it explicitly or ensure "
                    "flask-headless-auth is initialized first."
                )
        
        # Verify User model has SubscriptionMixin
        from flask_headless_payments.mixins import SubscriptionMixin
        if not any(isinstance(base, type) and issubclass(base, SubscriptionMixin) 
                   for base in self.user_model.__mro__):
            logger.warning(
                "User model does not include SubscriptionMixin. "
                "Please add SubscriptionMixin to your User model for subscription tracking. "
                "Example: class User(db.Model, SubscriptionMixin): ..."
            )
        
        # Validate custom models have required fields
        self._validate_models()
        
        # Create tables
        with app.app_context():
            self.db.create_all()
            logger.info("Payment database tables created")
    
    def _validate_models(self):
        """
        Validate that custom models have all required fields.
        
        This prevents runtime errors when the webhook_manager or other
        components try to access expected fields.
        """
        errors = []
        warnings = []
        
        # Required fields for WebhookEvent model (used by webhook_manager)
        webhook_required = {
            'stripe_event_id': 'String - Stripe event ID',
            'event_type': 'String - Event type (e.g., checkout.session.completed)',
            'data': 'JSON - Event data payload (MUST be named "data", not "event_data")',
            'processed': 'Boolean - Whether event has been processed',
            'error': 'Text - Error message if processing failed',
        }
        
        if self.webhook_event_model:
            model_columns = {c.name for c in self.webhook_event_model.__table__.columns}
            for field, description in webhook_required.items():
                if field not in model_columns:
                    errors.append(
                        f"WebhookEvent model missing required field '{field}' ({description})"
                    )
        
        # Required fields for Customer model
        customer_required = {
            'stripe_customer_id': 'String - Stripe customer ID',
            'user_id': 'Integer - Reference to User',
            'email': 'String - Customer email',
        }
        
        if self.customer_model:
            model_columns = {c.name for c in self.customer_model.__table__.columns}
            for field, description in customer_required.items():
                if field not in model_columns:
                    errors.append(
                        f"Customer model missing required field '{field}' ({description})"
                    )
        
        # Required fields for Payment model
        payment_required = {
            'user_id': 'Integer - Reference to User',
            'amount': 'Integer - Amount in cents',
            'status': 'String - Payment status',
        }
        
        if self.payment_model:
            model_columns = {c.name for c in self.payment_model.__table__.columns}
            for field, description in payment_required.items():
                if field not in model_columns:
                    warnings.append(
                        f"Payment model missing field '{field}' ({description})"
                    )
        
        # Log errors and warnings
        for warning in warnings:
            logger.warning(f"⚠️ {warning}")
        
        for error in errors:
            logger.error(f"❌ {error}")
        
        if errors:
            logger.error(
                "\n" + "="*60 + "\n"
                "FLASK-HEADLESS-PAYMENTS MODEL VALIDATION FAILED\n"
                "="*60 + "\n"
                "Your custom models are missing required fields.\n\n"
                "SOLUTION: Either:\n"
                "1. Inherit from the mixins (they auto-create columns):\n"
                "   class MyWebhookEvent(db.Model, WebhookEventMixin):\n"
                "       __tablename__ = 'my_webhook_events'\n"
                "       id = db.Column(db.Integer, primary_key=True)\n"
                "       # Mixin adds: data, processed, error, etc.\n\n"
                "2. Or don't pass custom models (use package defaults):\n"
                "   PaymentSvc(app, user_model=User)  # Uses default tables\n"
                "="*60
            )
    
    def _init_stripe(self, app):
        """Initialize Stripe."""
        stripe_key = app.config.get('STRIPE_API_KEY')
        if stripe_key:
            stripe.api_key = stripe_key
            stripe.api_version = app.config.get('STRIPE_API_VERSION', '2023-10-16')
            logger.info("Stripe initialized")
        else:
            logger.warning("Stripe API key not configured")
    
    def _init_managers(self, app):
        """Initialize manager instances."""
        from flask_headless_payments.managers import (
            SubscriptionManager, CheckoutManager, WebhookManager, PlanManager
        )
        
        # Subscription Manager
        self.subscription_manager = SubscriptionManager(
            db=self.db,
            user_model=self.user_model,
            customer_model=self.customer_model,
            payment_model=self.payment_model
        )
        
        # Checkout Manager
        self.checkout_manager = CheckoutManager(config=app.config)
        
        # Plan Manager
        if not self.plans:
            logger.warning("No plans configured. Define plans for subscription management.")
            self.plans = {'free': {'name': 'Free', 'price_id': None}}
        
        self.plan_manager = PlanManager(plans=self.plans)
        
        # Webhook Manager
        self.webhook_manager = WebhookManager(
            db=self.db,
            user_model=self.user_model,
            webhook_event_model=self.webhook_event_model,
            subscription_manager=self.subscription_manager
        )
        
        logger.info("Payment managers initialized")
    
    def _init_cors(self, app):
        """Initialize CORS."""
        from flask_cors import CORS
        
        cors_origins = app.config.get('PAYMENTSVC_CORS_ORIGINS', ['*'])
        
        if isinstance(cors_origins, str):
            cors_origins = cors_origins.split(',')
        
        CORS(
            app,
            origins=cors_origins,
            supports_credentials=True,
            allow_headers=['Content-Type', 'Authorization'],
            methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
        )
        logger.info("CORS initialized for payments")
    
    def _init_routes(self, app):
        """Register payment routes."""
        from flask_headless_payments.routes import create_payment_blueprint
        
        # Use provided url_prefix or fall back to config or default
        url_prefix = self.url_prefix or app.config.get('PAYMENTSVC_URL_PREFIX', '/api/payments')
        
        # Create payment blueprint with unique name and instance-level webhook secret
        payment_bp = create_payment_blueprint(
            user_model=self.user_model,
            customer_model=self.customer_model,
            payment_model=self.payment_model,
            webhook_event_model=self.webhook_event_model,
            subscription_manager=self.subscription_manager,
            checkout_manager=self.checkout_manager,
            webhook_manager=self.webhook_manager,
            plan_manager=self.plan_manager,
            config=app.config,
            blueprint_name=self.blueprint_name,  # Pass unique blueprint name
            webhook_secret=self.webhook_secret  # Pass instance-level webhook secret
        )
        
        app.register_blueprint(payment_bp, url_prefix=url_prefix)
        
        logger.info(f"Payment routes registered at {url_prefix} with blueprint '{self.blueprint_name}'")
    
    def register_webhook_handler(self, event_type: str, handler):
        """
        Register a custom webhook handler.
        
        Usage:
            def my_handler(event_data, db, user_model):
                # Custom logic
                pass
            
            payments.register_webhook_handler('invoice.paid', my_handler)
        
        Args:
            event_type: Stripe event type
            handler: Handler function
        """
        if self.webhook_manager:
            self.webhook_manager.register_handler(event_type, handler)

