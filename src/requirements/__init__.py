"""Shared trip requirement contracts and activity-aware checks."""

from .contract import Activity, Requirement, RequirementIntent, Scope, valid_condition
from .checks import activity_for, allowed, applicable, category_for, hard_result, scope_allows, scope_for

__all__ = ["Activity", "Requirement", "RequirementIntent", "Scope", "activity_for", "allowed", "applicable",
           "category_for", "hard_result", "scope_allows", "scope_for", "valid_condition"]
