"""One entry point for every method."""
from .calling import simulate_calling
from .pile import simulate_pile
from .stacks import simulate_stacks

METHODS = {
    "one_stack":  ("1 · One stack from one end", simulate_stacks),
    "two_stacks": ("2 · Two stacks, one from each end", simulate_stacks),
    "per_table":  ("3 · One stack per table", simulate_stacks),
    "calling":    ("4 · Calling names, lecturer walks", simulate_calling),
    "pile_desk":  ("5 · Pile on my desk, after class", simulate_pile),
    # "pile_door" (pile beside a door) is still in pile.py but no longer compared:
    # in practice it is the same method as the pile on the desk.
}


def run(method, room, P, seed, record=False):
    """Simulate one class. Returns (recorded frames or None, metrics dict)."""
    _, fn = METHODS[method]
    return fn(room, P, seed, method, record=record)
