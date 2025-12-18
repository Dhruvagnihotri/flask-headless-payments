"""
flask_headless_payments.managers.plan_manager
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Plan configuration and management.
"""

import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class PlanManager:
    """Manages subscription plans and access control."""
    
    def __init__(self, plans: Dict[str, Dict[str, Any]]):
        """
        Initialize plan manager.
        
        Args:
            plans: Dictionary of plan configurations
                Example:
                {
                    'free': {
                        'name': 'Free',
                        'price_id': None,
                        'features': ['feature1', 'feature2'],
                        'limits': {'api_calls': 100}
                    },
                    'pro': {
                        'name': 'Pro',
                        'price_id': 'price_xxx',
                        'features': ['feature1', 'feature2', 'feature3'],
                        'limits': {'api_calls': 1000}
                    }
                }
        """
        self.plans = plans
        self._validate_plans()
    
    def _validate_plans(self):
        """Validate plan configuration."""
        if not self.plans:
            raise ValueError("Plans configuration is required")
        
        if 'free' not in self.plans:
            logger.warning("No 'free' plan defined. Consider adding a free tier.")
        
        for plan_name, plan_config in self.plans.items():
            if 'name' not in plan_config:
                raise ValueError(f"Plan '{plan_name}' missing 'name' field")
    
    def get_plan(self, plan_name: str) -> Optional[Dict[str, Any]]:
        """
        Get plan configuration.
        
        Args:
            plan_name: Plan name
            
        Returns:
            dict: Plan configuration or None
        """
        return self.plans.get(plan_name)
    
    def get_all_plans(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all plans.
        
        Returns:
            dict: All plan configurations
        """
        return self.plans
    
    def plan_exists(self, plan_name: str) -> bool:
        """
        Check if plan exists.
        
        Args:
            plan_name: Plan name
            
        Returns:
            bool: True if plan exists
        """
        return plan_name in self.plans
    
    def get_plan_features(self, plan_name: str) -> List[str]:
        """
        Get features for a plan.
        
        Args:
            plan_name: Plan name
            
        Returns:
            list: List of features
        """
        plan = self.get_plan(plan_name)
        return plan.get('features', []) if plan else []
    
    def has_feature(self, plan_name: str, feature: str) -> bool:
        """
        Check if plan has a specific feature.
        
        Args:
            plan_name: Plan name
            feature: Feature name
            
        Returns:
            bool: True if plan has feature
        """
        features = self.get_plan_features(plan_name)
        return feature in features
    
    def get_plan_limit(self, plan_name: str, limit_key: str) -> Optional[int]:
        """
        Get limit value for a plan.
        
        Args:
            plan_name: Plan name
            limit_key: Limit key (e.g., 'api_calls')
            
        Returns:
            int: Limit value or None
        """
        plan = self.get_plan(plan_name)
        if not plan:
            return None
        limits = plan.get('limits', {})
        return limits.get(limit_key)
    
    def compare_plans(self, plan1: str, plan2: str) -> int:
        """
        Compare two plans to determine hierarchy.
        
        Args:
            plan1: First plan name
            plan2: Second plan name
            
        Returns:
            int: -1 if plan1 < plan2, 0 if equal, 1 if plan1 > plan2
        """
        # Define plan hierarchy (customize as needed)
        hierarchy = list(self.plans.keys())
        
        try:
            idx1 = hierarchy.index(plan1)
            idx2 = hierarchy.index(plan2)
            
            if idx1 < idx2:
                return -1
            elif idx1 > idx2:
                return 1
            else:
                return 0
        except ValueError:
            return 0
    
    def is_upgrade(self, from_plan: str, to_plan: str) -> bool:
        """
        Check if changing plans is an upgrade.
        
        Args:
            from_plan: Current plan
            to_plan: Target plan
            
        Returns:
            bool: True if upgrade
        """
        return self.compare_plans(from_plan, to_plan) < 0
    
    def is_downgrade(self, from_plan: str, to_plan: str) -> bool:
        """
        Check if changing plans is a downgrade.
        
        Args:
            from_plan: Current plan
            to_plan: Target plan
            
        Returns:
            bool: True if downgrade
        """
        return self.compare_plans(from_plan, to_plan) > 0
    
    def get_price_id(self, plan_name: str) -> Optional[str]:
        """
        Get Stripe price ID for a plan.
        
        Args:
            plan_name: Plan name
            
        Returns:
            str: Stripe price ID or None
        """
        plan = self.get_plan(plan_name)
        return plan.get('price_id') if plan else None

