"""
Contract Clause Analyzer backend package.
"""

# Compatibility shim: pydantic v1 + Python 3.12 ForwardRef signature
import inspect
import typing

_orig_eval = typing.ForwardRef._evaluate  # type: ignore[attr-defined]
_params = inspect.signature(_orig_eval).parameters


def _patched_forward_ref(self, globalns, localns, *args, **kwargs):  # type: ignore[override]
    try:
        return _orig_eval(self, globalns, localns, *args, **kwargs)
    except TypeError as exc:
        missing_recursive_guard = "recursive_guard" in str(exc)
        should_add_recursive_guard = (
            "recursive_guard" in _params
            and "recursive_guard" not in kwargs
            and not args
            and missing_recursive_guard
        )
        if should_add_recursive_guard:
            return _orig_eval(self, globalns, localns, recursive_guard=set(), **kwargs)
        raise


typing.ForwardRef._evaluate = _patched_forward_ref  # type: ignore[assignment]