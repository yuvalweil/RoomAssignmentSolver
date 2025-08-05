# logic/__init__.py

from .solver   import assign_rooms, assign_per_type
from .validate import validate_constraints

__all__ = [
    "assign_rooms",
    "assign_per_type",
    "validate_constraints",
]
