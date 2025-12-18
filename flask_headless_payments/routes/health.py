"""
flask_headless_payments.routes.health
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Health check and monitoring endpoints.
"""

from flask import Blueprint, jsonify
import logging

logger = logging.getLogger(__name__)


def create_health_blueprint(health_check, blueprint_name='paymentsvc_health'):
    """
    Create health check blueprint.
    
    Args:
        health_check: HealthCheck instance
        blueprint_name: Blueprint name
    
    Returns:
        Blueprint: Health check blueprint
    """
    
    bp = Blueprint(blueprint_name, __name__)
    
    @bp.route('/health', methods=['GET'])
    def health():
        """Basic health check endpoint."""
        return jsonify({'status': 'ok'}), 200
    
    @bp.route('/health/ready', methods=['GET'])
    def readiness():
        """Readiness check - is the service ready to accept requests?"""
        results = health_check.run_all_checks()
        
        status_code = 200 if results['status'] == 'healthy' else 503
        return jsonify(results), status_code
    
    @bp.route('/health/live', methods=['GET'])
    def liveness():
        """Liveness check - is the service alive?"""
        return jsonify({
            'status': 'alive',
            'service': 'flask-headless-payments'
        }), 200
    
    @bp.route('/metrics', methods=['GET'])
    def metrics():
        """Basic metrics endpoint."""
        # In production, integrate with Prometheus or similar
        return jsonify({
            'service': 'flask-headless-payments',
            'version': '0.1.0',
            'metrics_available': False,
            'note': 'Integrate with Prometheus for production metrics'
        }), 200
    
    return bp

