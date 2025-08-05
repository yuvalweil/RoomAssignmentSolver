# logic/__init__.py

# Always import assign_rooms and validate_constraints
from .solver import assign_rooms
from .validate import validate_constraints

# Attempt to import assign_per_type; if it doesn't exist, alias it to assign_rooms
try:
    from .solver import assign_per_type
except ImportError:
    assign_per_type = assign_rooms

__all__ = [
    "assign_rooms",
    "validate_constraints",
    "assign_per_type",  # for backward compatibility
]
