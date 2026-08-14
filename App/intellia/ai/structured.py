"""Dataclass <-> JSON Schema, without pydantic.

``models`` is imported on every code path, including mock-only mode where ``anthropic``
(and therefore pydantic) may not be installed -- so the structured-output layer is built
on stdlib dataclasses instead.

Note: this module calls ``typing.get_type_hints`` at runtime. On Python 3.9 a PEP 604
union (``str | None``) raises ``TypeError`` there even with ``from __future__ import
annotations``, which is why the codebase uses ``Optional[str]`` everywhere.
"""

from __future__ import annotations

import dataclasses
import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union, get_type_hints

try:
    from typing import get_args, get_origin
except ImportError:  # pragma: no cover - 3.7 only
    def get_args(tp):  # type: ignore
        return getattr(tp, "__args__", ())

    def get_origin(tp):  # type: ignore
        return getattr(tp, "__origin__", None)

_PRIMITIVES = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _is_optional(tp: Any) -> Tuple[bool, Any]:
    if get_origin(tp) is Union:
        args = [a for a in get_args(tp) if a is not type(None)]  # noqa: E721
        if len(args) < len(get_args(tp)):
            return True, args[0] if len(args) == 1 else Union[tuple(args)]
    return False, tp


def schema_for(cls: Any) -> Dict[str, Any]:
    """JSON Schema for a dataclass. Optional fields are still emitted (nullable)."""
    if not dataclasses.is_dataclass(cls):
        raise TypeError("schema_for expects a dataclass, got {!r}".format(cls))

    hints = get_type_hints(cls)
    properties: Dict[str, Any] = {}
    required: List[str] = []

    for field in dataclasses.fields(cls):
        tp = hints.get(field.name, str)
        optional, inner = _is_optional(tp)
        properties[field.name] = _schema_for_type(inner)
        has_default = (field.default is not dataclasses.MISSING
                       or field.default_factory is not dataclasses.MISSING)  # type: ignore
        if not optional and not has_default:
            required.append(field.name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _schema_for_type(tp: Any) -> Dict[str, Any]:
    if tp in _PRIMITIVES:
        return {"type": _PRIMITIVES[tp]}
    if dataclasses.is_dataclass(tp):
        return schema_for(tp)
    origin = get_origin(tp)
    if origin in (list, List):
        args = get_args(tp)
        return {"type": "array", "items": _schema_for_type(args[0]) if args else {"type": "string"}}
    if origin in (dict, Dict):
        return {"type": "object"}
    return {"type": "string"}


# -- coercion ------------------------------------------------------------------------


def coerce(payload: Any, cls: Any, path: str = "") -> Tuple[Any, List[str]]:
    """Build ``cls`` from a raw payload, collecting path-qualified errors."""
    errors: List[str] = []
    if not isinstance(payload, dict):
        return None, ["{}: expected an object, got {}".format(path or "root", type(payload).__name__)]

    hints = get_type_hints(cls)
    kwargs: Dict[str, Any] = {}

    for field in dataclasses.fields(cls):
        tp = hints.get(field.name, str)
        optional, inner = _is_optional(tp)
        here = "{}.{}".format(path, field.name) if path else field.name

        if field.name not in payload or payload[field.name] is None:
            if field.default is not dataclasses.MISSING:
                kwargs[field.name] = field.default
            elif field.default_factory is not dataclasses.MISSING:  # type: ignore
                kwargs[field.name] = field.default_factory()      # type: ignore
            elif optional:
                kwargs[field.name] = None
            else:
                errors.append("{}: missing required field".format(here))
            continue

        value, sub_errors = _coerce_value(payload[field.name], inner, here)
        errors.extend(sub_errors)
        kwargs[field.name] = value

    if errors:
        return None, errors
    try:
        return cls(**kwargs), []
    except TypeError as exc:
        return None, ["{}: {}".format(path or "root", exc)]


def _coerce_value(value: Any, tp: Any, path: str) -> Tuple[Any, List[str]]:
    if dataclasses.is_dataclass(tp):
        return coerce(value, tp, path)

    origin = get_origin(tp)
    if origin in (list, List):
        if not isinstance(value, list):
            return [], ["{}: expected a list".format(path)]
        args = get_args(tp)
        item_type = args[0] if args else str
        out, errors = [], []
        for i, item in enumerate(value):
            coerced, sub = _coerce_value(item, item_type, "{}[{}]".format(path, i))
            errors.extend(sub)
            if not sub:
                out.append(coerced)
        return out, errors

    if tp is str:
        return ("" if value is None else str(value)), []
    if tp is bool:
        return bool(value), []
    if tp in (int, float):
        try:
            return (int(value) if tp is int else float(value)), []
        except (TypeError, ValueError):
            return (0 if tp is int else 0.0), ["{}: expected a number, got {!r}".format(path, value)]
    return value, []


# -- extraction ----------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Optional[Any]:
    """Pull the first JSON object/array out of a model response."""
    if not text:
        return None
    candidate = text.strip()

    fence = _FENCE_RE.search(candidate)
    if fence:
        candidate = fence.group(1).strip()

    try:
        return json.loads(candidate)
    except ValueError:
        pass

    for opener, closer in (("{", "}"), ("[", "]")):
        start = candidate.find(opener)
        if start == -1:
            continue
        depth, in_string, escape = 0, False, False
        for i in range(start, len(candidate)):
            ch = candidate[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(candidate[start:i + 1])
                    except ValueError:
                        break
    return None
