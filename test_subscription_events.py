"""
Isolated test for the SubscriptionEvent history ledger (models.py,
core.py, webhook_manager.py). In-memory SQLite, no real Stripe API
calls — webhook handlers are invoked directly with hand-built payload
dicts shaped like real Stripe webhook JSON.

Run: python3 test_subscription_events.py
"""

import sys
from datetime import datetime, timezone


def _make_app_and_payments(with_custom_subscription_event_model=False):
    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy
    from flask_headless_payments import PaymentSvc

    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-secret'
    app.config['JWT_SECRET_KEY'] = 'test-jwt-secret'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['STRIPE_API_KEY'] = 'sk_test_dummy'
    app.config['STRIPE_WEBHOOK_SECRET'] = 'whsec_dummy'

    db = SQLAlchemy(app)

    class User(db.Model):
        __tablename__ = 'users'
        id = db.Column(db.Integer, primary_key=True)
        email = db.Column(db.String(255), unique=True, nullable=False)
        stripe_customer_id = db.Column(db.String(255), unique=True)
        stripe_subscription_id = db.Column(db.String(255))
        plan_name = db.Column(db.String(50))
        plan_status = db.Column(db.String(50))
        current_period_start = db.Column(db.DateTime)
        current_period_end = db.Column(db.DateTime)
        trial_start = db.Column(db.DateTime)
        trial_end = db.Column(db.DateTime)
        cancel_at_period_end = db.Column(db.Boolean, default=False)

    CustomSubscriptionEvent = None
    if with_custom_subscription_event_model:
        class CustomSubscriptionEvent(db.Model):
            __tablename__ = 'custom_subscription_events'
            id = db.Column(db.Integer, primary_key=True)
            user_id = db.Column(db.Integer, nullable=False)
            stripe_subscription_id = db.Column(db.String(255))
            event_type = db.Column(db.String(20), nullable=False)
            plan_name = db.Column(db.String(100))
            plan_status = db.Column(db.String(50))
            current_period_start = db.Column(db.DateTime)
            current_period_end = db.Column(db.DateTime)
            cancel_at_period_end = db.Column(db.Boolean)

    kwargs = dict(user_model=User, plans={'pro': {'name': 'Pro', 'price_id': 'price_123'}})
    if with_custom_subscription_event_model:
        kwargs['subscription_event_model'] = CustomSubscriptionEvent

    with app.app_context():
        payments = PaymentSvc(app, **kwargs)

    return app, db, User, payments


def _subscription_payload(sub_id, customer_id, status, period_start_ts, period_end_ts,
                           cancel_at_period_end=False, plan_name='pro'):
    return {
        'id': sub_id,
        'customer': customer_id,
        'status': status,
        'cancel_at_period_end': cancel_at_period_end,
        'current_period_start': period_start_ts,
        'current_period_end': period_end_ts,
        'items': {
            'data': [
                {'price': {'metadata': {'plan_name': plan_name}}}
            ]
        },
    }


def test_default_creation_and_created_updated_canceled_flow():
    app, db, User, payments = _make_app_and_payments()

    with app.app_context():
        assert payments.subscription_event_model is not None, \
            "default SubscriptionEvent model should be created when no override is given"
        assert payments.subscription_event_model.__tablename__ == 'paymentsvc_subscription_events'

        user = User(email='alice@example.com', stripe_customer_id='cus_alice')
        db.session.add(user)
        db.session.commit()

        t0 = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
        t1 = int(datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp())

        # customer.subscription.created
        created_payload = _subscription_payload('sub_1', 'cus_alice', 'active', t0, t1)
        returned_user = payments.webhook_manager._handle_subscription_created(created_payload, commit=True)
        assert returned_user is not None and returned_user.id == user.id

        events = payments.subscription_event_model.query.filter_by(user_id=user.id).order_by(
            payments.subscription_event_model.id
        ).all()
        assert len(events) == 1, f"expected 1 event after created, got {len(events)}"
        assert events[0].event_type == 'created'
        assert events[0].plan_name == 'pro'
        assert events[0].plan_status == 'active'
        assert events[0].stripe_subscription_id == 'sub_1'
        assert events[0].cancel_at_period_end is False
        assert events[0].current_period_start is not None
        assert events[0].current_period_end is not None

        # customer.subscription.updated (plan change)
        t2 = int(datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp())
        updated_payload = _subscription_payload('sub_1', 'cus_alice', 'active', t1, t2, plan_name='enterprise')
        payments.webhook_manager._handle_subscription_updated(updated_payload, commit=True)

        events = payments.subscription_event_model.query.filter_by(user_id=user.id).order_by(
            payments.subscription_event_model.id
        ).all()
        assert len(events) == 2, f"expected 2 events after updated, got {len(events)}"
        assert events[1].event_type == 'updated'
        assert events[1].plan_name == 'enterprise'

        # Current-state fields on User itself must still reflect latest values —
        # the ledger must be additive, never a replacement for the hot-path columns.
        assert user.plan_name == 'enterprise'
        assert user.plan_status == 'active'

        # customer.subscription.deleted (cancellation) — deliberately uses a
        # DIFFERENT current_period_end (t3) and cancel_at_period_end=False
        # (an immediate, not at-period-end, cancellation) than the prior
        # updated event, to catch the regression where the ledger snapshot
        # was written from stale user fields instead of this payload.
        t3 = int(datetime(2026, 3, 5, tzinfo=timezone.utc).timestamp())
        deleted_payload = _subscription_payload(
            'sub_1', 'cus_alice', 'canceled', t2, t3, cancel_at_period_end=False, plan_name='enterprise'
        )
        payments.webhook_manager._handle_subscription_deleted(deleted_payload, commit=True)

        events = payments.subscription_event_model.query.filter_by(user_id=user.id).order_by(
            payments.subscription_event_model.id
        ).all()
        assert len(events) == 3, f"expected 3 events after deleted, got {len(events)}"
        assert events[2].event_type == 'canceled'
        assert events[2].plan_status == 'canceled'
        assert events[2].stripe_subscription_id == 'sub_1', \
            "canceled event must still record which subscription was canceled"
        assert events[2].current_period_end is not None
        assert events[2].current_period_end.year == 2026 and events[2].current_period_end.month == 3 \
            and events[2].current_period_end.day == 5, \
            "canceled event must snapshot the DELETED payload's period end, not a stale value from the prior updated event"
        assert events[2].cancel_at_period_end is False, \
            "canceled event must reflect the payload's actual cancel_at_period_end, not a hardcoded True"

        # Post-cancellation current-state: subscription_id cleared, status canceled —
        # unchanged behavior from before this fix.
        assert user.stripe_subscription_id is None
        assert user.plan_status == 'canceled'

    print("PASS: default creation + created/updated/canceled event flow")


def test_skip_when_custom_model_provided():
    app, db, User, payments = _make_app_and_payments(with_custom_subscription_event_model=True)

    with app.app_context():
        from flask_headless_payments.models import _default_models_cache
        # No default paymentsvc_subscription_events table should have been
        # created/registered for this db instance.
        assert 'paymentsvc_subscription_events' not in db.metadata.tables, \
            "default SubscriptionEvent table must not be created when an override is provided"

        assert payments.subscription_event_model.__tablename__ == 'custom_subscription_events'

        user = User(email='bob@example.com', stripe_customer_id='cus_bob')
        db.session.add(user)
        db.session.commit()

        t0 = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
        t1 = int(datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp())
        payload = _subscription_payload('sub_9', 'cus_bob', 'active', t0, t1)
        payments.webhook_manager._handle_subscription_created(payload, commit=True)

        events = payments.subscription_event_model.query.filter_by(user_id=user.id).all()
        assert len(events) == 1
        assert events[0].event_type == 'created'

    print("PASS: skip default + use custom subscription_event_model")


def test_noop_when_no_model_configured_at_all():
    """WebhookManager must tolerate subscription_event_model=None entirely
    (e.g. an app pinned to an older flask-headless-payments release path
    that never passed the new kwarg) — should update the user's
    current-state fields exactly as before and simply not record history,
    never raise."""
    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy
    from flask_headless_payments.managers.webhook_manager import WebhookManager
    from flask_headless_payments.managers.subscription_manager import SubscriptionManager

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    db = SQLAlchemy(app)

    class User(db.Model):
        __tablename__ = 'users'
        id = db.Column(db.Integer, primary_key=True)
        email = db.Column(db.String(255), unique=True, nullable=False)
        stripe_customer_id = db.Column(db.String(255), unique=True)
        stripe_subscription_id = db.Column(db.String(255))
        plan_name = db.Column(db.String(50))
        plan_status = db.Column(db.String(50))
        current_period_start = db.Column(db.DateTime)
        current_period_end = db.Column(db.DateTime)
        cancel_at_period_end = db.Column(db.Boolean, default=False)

    with app.app_context():
        db.create_all()
        user = User(email='carol@example.com', stripe_customer_id='cus_carol')
        db.session.add(user)
        db.session.commit()

        sub_manager = SubscriptionManager(db=db, user_model=User, customer_model=None, payment_model=None)
        wm = WebhookManager(db=db, user_model=User, webhook_event_model=None,
                             subscription_manager=sub_manager, payment_model=None,
                             subscription_event_model=None)

        t0 = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
        t1 = int(datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp())
        payload = _subscription_payload('sub_5', 'cus_carol', 'active', t0, t1)
        returned_user = wm._handle_subscription_created(payload, commit=True)

        assert returned_user is not None
        assert user.plan_status == 'active', "current-state update must still happen with no history model"

    print("PASS: no-op safely when subscription_event_model is None")


if __name__ == '__main__':
    failures = []
    for test in (
        test_default_creation_and_created_updated_canceled_flow,
        test_skip_when_custom_model_provided,
        test_noop_when_no_model_configured_at_all,
    ):
        try:
            test()
        except AssertionError as e:
            failures.append((test.__name__, str(e)))
            print(f"FAIL: {test.__name__}: {e}")
        except Exception as e:
            failures.append((test.__name__, repr(e)))
            print(f"ERROR: {test.__name__}: {e!r}")

    if failures:
        print(f"\n{len(failures)} test(s) failed")
        sys.exit(1)
    else:
        print("\nAll tests passed")
