"""Auto-discover Strategy subclasses from a directory."""

import importlib.util
import inspect
import os
import warnings

from bot.strategies.base import Strategy

_SKIP = {"base.py", "loader.py", "__init__.py"}


def load_strategies(directory):
    found = {}
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".py") or fname in _SKIP:
            continue
        path = os.path.join(directory, fname)
        mod_name = f"_strategy_{fname[:-3]}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            warnings.warn(f"failed to load strategy file {fname}: {e}")
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Strategy) and obj is not Strategy:
                instance = obj()
                found[instance.name] = instance
    return found
