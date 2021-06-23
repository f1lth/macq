from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
from . import Fluent


class State:
    """State in a trace.

    A dict-like object. Maps `Fluent` objects to boolean values, representing
    the state for a `Step` in a `Trace`.

    Attributes:
        fluents (dict):
            A mapping of `Fluent` objects to their value in this state.
    """

    def __init__(self, fluents: Dict[Fluent, bool] = {}):
        """Initializes State with an optional fluent-value mapping.

        Args:
            fluents (dict):
                Optional; A mapping of `Fluent` objects to their value in this
                state. Defaults to an empty `dict`.
        """
        self.fluents = fluents

    def __eq__(self, other):
        if not isinstance(other, State):
            return False
        return self.fluents == other.fluents

    def __str__(self):
        return ", ".join([str(fluent) for (fluent, value) in self.items() if value])

    def __hash__(self):
        return hash(self.details())

    def __len__(self):
        return len(self.fluents)

    def __setitem__(self, key: Fluent, value: bool):
        self.fluents[key] = value

    def __getitem__(self, key: Fluent):
        return self.fluents[key]

    def __delitem__(self, key: Fluent):
        del self.fluents[key]

    def __iter__(self):
        return iter(self.fluents)

    def __contains__(self, key):
        return self.fluents[key]

    def clear(self):
        return self.fluents.clear()

    def copy(self):
        return self.fluents.copy()

    def has_key(self, k):
        return k in self.fluents

    def update(self, *args, **kwargs):
        return self.fluents.update(*args, **kwargs)

    def keys(self):
        return self.fluents.keys()

    def values(self):
        return self.fluents.values()

    def items(self):
        return self.fluents.items()

    def details(self):
        string = ""
        for fluent, value in self.items():
            string += f"{str(fluent)} ({value}), "
        return string[:-2]

    def clone(self):
        return State(self.fluents)

    def holds(self, fluent: str):
        fluents = dict(map(lambda f: (f.name, f), self.keys()))
        if fluent in fluents.keys():
            return self[fluents[fluent]]
