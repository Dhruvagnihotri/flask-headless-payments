"""
Regression tests for payment_intent.succeeded / invoice.* user resolution
and the Payment audit-record upsert (webhook_manager.py).

Real bug fixed 2026-10-01: a customerless mode='payment' Checkout Session
(a guest/one-time purchase where the app never creates a Stripe Customer -
e.g. pdfwhiz's $2.99 one-time Pro Pass) has no `customer` field on its
PaymentIntent at all. _handle_payment_intent_succeeded only ever resolved
a user via the Customer chain, so `user` was always None for this case,
and _upsert_payment_record then inserted NULL into Payment.user_id (NOT
NULL on both this package's default model and every consuming app's
override seen so far) - a real IntegrityError in production, returned to
Stripe as a 500, retried forever. The actual access grant was unaffected
(handled separately via the app's own checkout.session.completed
callback + session metadata) - only this audit-log table broke.

Fix has two parts, both covered below:
1. _resolve_payment_user falls back to metadata.user_id when the Customer
   chain resolves nothing (same pattern consuming apps already use for
   checkout.session.completed).
2. _upsert_payment_record skips creating a row (logs a warning, returns
   None) rather than inserting a NULL user_id when NEITHER resolves -
   the actual crash fix, independent of whether metadata happens to help.

In-memory SQLite, no real Stripe API calls - handlers invoked directly
with hand-built payload dicts shaped like real Stripe webhook JSON.

Run: python3 test_payment_intent_handling.py
"""

import sys


def _make_app_and_payments():
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

    with app.app_context():
        # Deliberately NOT passing payment_model - this exercises the
        # package's own DEFAULT Payment model (models.py's Payment,
        # __tablename__='paymentsvc_payments'), which has the same
        # user_id NOT NULL constraint every real consuming app has.
        payments = PaymentSvc(app, user_model=User, plans={'pro': {'name': 'Pro', 'price_id': 'price_123'}})

    return app, db, User, payments


def _payment_intent_payload(pi_id, customer_id=None, metadata=None, amount=299):
    return {
        'id': pi_id,
        'customer': customer_id,
        'invoice': None,
        'amount_received': amount,
        'amount': amount,
        'currency': 'usd',
        'description': 'Test payment',
        'metadata': metadata or {},
    }


def _invoice_payload(invoice_id, customer_id=None, metadata=None, payment_intent_id=None, amount=299):
    return {
        'id': invoice_id,
        'customer': customer_id,
        'payment_intent': payment_intent_id,
        'amount_paid': amount,
        'amount_due': amount,
        'currency': 'usd',
        'hosted_invoice_url': None,
        'description': 'Test invoice',
        'metadata': metadata or {},
    }


def test_customer_resolvable_payment_creates_record():
    """Regression guard: the existing, already-working Customer-chain
    resolution path (subscription payments, or any mode='payment' session
    created through CheckoutManager, which always attaches a Customer)
    must still work exactly as before this fix."""
    app, db, User, payments = _make_app_and_payments()

    with app.app_context():
        user = User(email='alice@example.com', stripe_customer_id='cus_alice')
        db.session.add(user)
        db.session.commit()

        payload = _payment_intent_payload('pi_1', customer_id='cus_alice')
        returned_user = payments.webhook_manager._handle_payment_intent_succeeded(payload, commit=True)

        assert returned_user is not None and returned_user.id == user.id

        row = payments.payment_model.query.filter_by(stripe_payment_intent_id='pi_1').first()
        assert row is not None, "Payment record must be created when a user resolves via Customer"
        assert row.user_id == user.id
        assert row.amount == 299
        assert row.status == 'succeeded'

    print("PASS: customer-resolvable payment_intent.succeeded creates a correctly-attributed Payment record")


def test_customerless_payment_resolves_via_metadata_fallback():
    """The actual improvement: a guest/one-time purchase with no Stripe
    Customer, but whose PaymentIntent DOES carry metadata.user_id (either
    because CheckoutManager's new payment_intent_data propagation set it,
    or because the app set it directly) must still get correctly
    attributed, not silently skipped."""
    app, db, User, payments = _make_app_and_payments()

    with app.app_context():
        user = User(email='bob@example.com', stripe_customer_id=None)
        db.session.add(user)
        db.session.commit()

        payload = _payment_intent_payload('pi_2', customer_id=None, metadata={'user_id': str(user.id)})
        returned_user = payments.webhook_manager._handle_payment_intent_succeeded(payload, commit=True)

        assert returned_user is not None and returned_user.id == user.id, \
            "metadata.user_id fallback must resolve the user when there's no Stripe Customer at all"

        row = payments.payment_model.query.filter_by(stripe_payment_intent_id='pi_2').first()
        assert row is not None
        assert row.user_id == user.id

    print("PASS: customerless payment_intent.succeeded resolves user via metadata.user_id fallback")


def test_customerless_payment_with_no_metadata_skips_without_crashing():
    """THE crash fix. No Customer, no metadata.user_id either - previously
    this inserted NULL into a NOT NULL user_id column and raised
    IntegrityError (which the real webhook route turns into a 500, and
    Stripe retries forever). Must now skip cleanly: no exception, no row,
    just a logged warning."""
    app, db, User, payments = _make_app_and_payments()

    with app.app_context():
        payload = _payment_intent_payload('pi_3', customer_id=None, metadata={})

        # Must not raise - this is the actual regression this test guards.
        returned_user = payments.webhook_manager._handle_payment_intent_succeeded(payload, commit=True)

        assert returned_user is None
        row = payments.payment_model.query.filter_by(stripe_payment_intent_id='pi_3').first()
        assert row is None, "no Payment row should be created when no user can be attributed"

    print("PASS: customerless payment_intent.succeeded with no metadata skips the audit record instead of crashing")


def test_customerless_payment_with_garbage_metadata_user_id_skips_without_crashing():
    """Defense against a malformed/unexpected metadata.user_id (e.g. a
    non-numeric string) - must degrade to the same safe skip, never raise."""
    app, db, User, payments = _make_app_and_payments()

    with app.app_context():
        payload = _payment_intent_payload('pi_4', customer_id=None, metadata={'user_id': 'not-a-number'})

        returned_user = payments.webhook_manager._handle_payment_intent_succeeded(payload, commit=True)

        assert returned_user is None
        row = payments.payment_model.query.filter_by(stripe_payment_intent_id='pi_4').first()
        assert row is None

    print("PASS: garbage metadata.user_id degrades to a safe skip, never raises")


def test_existing_row_update_path_unaffected_by_user_resolution():
    """The update-existing-row branch (a Stripe redelivery, or the other
    event of the invoice/payment_intent pair arriving second) must keep
    working even when the SECOND event's own user-resolution would have
    failed on its own - it should just update status on the row created by
    whichever event arrived first, never re-check user resolution."""
    app, db, User, payments = _make_app_and_payments()

    with app.app_context():
        user = User(email='carol@example.com', stripe_customer_id='cus_carol')
        db.session.add(user)
        db.session.commit()

        first = _payment_intent_payload('pi_5', customer_id='cus_carol')
        payments.webhook_manager._handle_payment_intent_succeeded(first, commit=True)

        # Redelivery of the same event, this time with the customer field
        # stripped out of the payload for some reason (Stripe doesn't
        # really do this, but it proves the existing-row path doesn't
        # re-derive user_id from scratch and isn't vulnerable to the same
        # NULL-insert bug on an update).
        redelivered = _payment_intent_payload('pi_5', customer_id=None)
        redelivered['description'] = 'updated description'
        payments.webhook_manager._handle_payment_intent_succeeded(redelivered, commit=True)

        rows = payments.payment_model.query.filter_by(stripe_payment_intent_id='pi_5').all()
        assert len(rows) == 1, "redelivery must update the existing row, never create a second one"
        assert rows[0].user_id == user.id, "existing row's user_id must be preserved across a redelivery"

    print("PASS: existing-row update path is unaffected by a redelivery's own user resolution")


def test_invoice_paid_resolves_via_metadata_fallback():
    """_handle_invoice_paid was refactored to use the same
    _resolve_payment_user helper as the PaymentIntent path. Invoices almost
    always carry a Customer in practice (Stripe requires one for
    subscriptions), so this fallback is mostly defense-in-depth here rather
    than fixing a live bug the way the PaymentIntent case did - but the
    refactor touched this handler too, so it needs its own direct test
    rather than relying on the PaymentIntent tests to imply it works."""
    app, db, User, payments = _make_app_and_payments()

    with app.app_context():
        user = User(email='dave@example.com', stripe_customer_id=None)
        db.session.add(user)
        db.session.commit()

        payload = _invoice_payload('in_1', customer_id=None, metadata={'user_id': str(user.id)},
                                    payment_intent_id='pi_in_1')
        returned_user = payments.webhook_manager._handle_invoice_paid(payload, commit=True)

        assert returned_user is not None and returned_user.id == user.id
        row = payments.payment_model.query.filter_by(stripe_payment_intent_id='pi_in_1').first()
        assert row is not None
        assert row.user_id == user.id

    print("PASS: invoice.payment_succeeded resolves user via metadata.user_id fallback")


def test_invoice_failed_with_no_resolvable_user_skips_without_crashing():
    """Mirror of the PaymentIntent crash-fix test, for the other handler
    that was refactored to share the same guarded _upsert_payment_record
    path. No Customer, no metadata.user_id - must skip cleanly, never
    raise IntegrityError."""
    app, db, User, payments = _make_app_and_payments()

    with app.app_context():
        payload = _invoice_payload('in_2', customer_id=None, metadata={}, payment_intent_id='pi_in_2')

        returned_user = payments.webhook_manager._handle_invoice_failed(payload, commit=True)

        assert returned_user is None
        row = payments.payment_model.query.filter_by(stripe_payment_intent_id='pi_in_2').first()
        assert row is None

    print("PASS: invoice.payment_failed with no resolvable user skips the audit record instead of crashing")


if __name__ == '__main__':
    failures = []
    for test in (
        test_customer_resolvable_payment_creates_record,
        test_customerless_payment_resolves_via_metadata_fallback,
        test_customerless_payment_with_no_metadata_skips_without_crashing,
        test_customerless_payment_with_garbage_metadata_user_id_skips_without_crashing,
        test_existing_row_update_path_unaffected_by_user_resolution,
        test_invoice_paid_resolves_via_metadata_fallback,
        test_invoice_failed_with_no_resolvable_user_skips_without_crashing,
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
