# logic/__init__.py

from .solver   import assign_rooms
from .validate import validate_constraints

# Provide a backward‐compatible alias for assign_per_type.
try:
    from .solver import assign_per_type
except ImportError:
    assign_per_type = assign_rooms

__all__ = [
    "assign_rooms",
    "validate_constraints",
    "assign_per_type",
]
