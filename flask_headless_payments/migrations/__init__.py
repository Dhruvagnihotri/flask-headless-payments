"""
flask_headless_payments.migrations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Database migration support using Flask-Migrate.
"""

from flask_migrate import Migrate


def init_migrations(app, db):
    """
    Initialize Flask-Migrate for database migrations.
    
    Usage:
        from flask_headless_payments.migrations import init_migrations
        init_migrations(app, db)
    
    Then run migrations:
        flask db init
        flask db migrate -m "Initial migration"
        flask db upgrade
    
    Args:
        app: Flask application
        db: SQLAlchemy database instance
    """
    migrate = Migrate(app, db, directory='migrations_paymentsvc')
    return migrate

