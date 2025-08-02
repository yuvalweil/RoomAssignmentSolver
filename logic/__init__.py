# logic/__init__.py
from .solver import assign_rooms, assign_per_type   # <- use the new solver
from .validate import validate_constraints
from .calendar_store import rebuild_calendar_from_assignments
from .diagnostics import explain_soft_constraints
from .utils import are_serial

__all__ = [
    "assign_rooms",
    "assign_per_type",
    "validate_constraints",
    "rebuild_calendar_from_assignments",
    "explain_soft_constraints",
    "are_serial",
]
