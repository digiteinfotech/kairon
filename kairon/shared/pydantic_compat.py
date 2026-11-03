"""Pydantic v2 helpers that keep Kairon's v1 request-validation behavior.

v1 treated ``field: T = None`` as optional and still ran root validators when a
field failed (``skip_on_failure=False``). v2 rejects that default and skips
model validators after a field error. ``KaironModel`` re-runs ``mode="after"``
validators on that failure and marks model-level errors with ``__root__``.

The wrap is installed from ``__get_pydantic_core_schema__`` so it sits outside
child ``mode="after"`` validators. A ``model_validator(mode="wrap")`` on this
base is collected first and would run inside those validators.
"""
import json
import re

from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticUndefined, core_schema


def _wrap_callable(schema):
    if not isinstance(schema, dict) or schema.get("type") != "function-wrap":
        return None
    function = schema.get("function")
    while isinstance(function, dict):
        function = function.get("function")
    return function


def _is_kairon_root_wrap(schema) -> bool:
    return bool(getattr(_wrap_callable(schema), "__kairon_root_wrap__", False))


def _v1_root_on_failure(cls, values, handler):
    try:
        return handler(values)
    except ValidationError as exc:
        errors = list(exc.errors())
        if not isinstance(values, dict):
            if not _has_empty_value_error(errors):
                raise
            raise ValidationError.from_exception_data(
                cls.__name__, _rootify(errors)
            )

        failed = _failed_fields(errors)
        extra = _rerun_after_validators(cls, values, failed) if failed else []
        if not extra and not _has_empty_value_error(errors):
            raise
        raise ValidationError.from_exception_data(
            cls.__name__, _rootify(errors) + extra
        )


class KaironModel(BaseModel):
    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        schema = handler(source)
        # Nested fields ask for this schema again after the class schema is cached.
        # handler() then returns the already wrapped schema. Wrapping it twice
        # reruns mode="after" validators and duplicates __root__ errors.
        if _is_kairon_root_wrap(schema):
            return schema

        def _wrap(values, inner):
            return _v1_root_on_failure(cls, values, inner)

        _wrap.__kairon_root_wrap__ = True
        return core_schema.no_info_wrap_validator_function(_wrap, schema)


def v1_validation_errors(errors) -> list:
    """Map pydantic v2 errors to the JSON-safe v1 ``message`` list the API returns."""
    translated = []
    for err in errors:
        loc = [part for part in (err.get("loc") or ())]
        kind = err.get("type")
        msg = err.get("msg") or ""
        ctx = err.get("ctx") or {}
        incoming = err.get("input", PydanticUndefined)
        if kind == "missing":
            translated.append(
                {"loc": loc, "msg": "field required", "type": "value_error.missing"}
            )
        elif kind in _TYPE_ERRORS and incoming is None:
            translated.append(
                {
                    "loc": loc,
                    "msg": "none is not an allowed value",
                    "type": "type_error.none.not_allowed",
                }
            )
        elif kind == "list_type":
            translated.append(
                {
                    "loc": loc,
                    "msg": "value is not a valid list",
                    "type": "type_error.list",
                }
            )
        elif kind == "dict_type":
            translated.append(
                {
                    "loc": loc,
                    "msg": "value is not a valid dict",
                    "type": "type_error.dict",
                }
            )
        elif kind == "enum":
            expected = ctx.get("expected") or ""
            translated.append(
                {
                    "loc": loc,
                    "msg": "value is not a valid enumeration member; permitted: "
                    + expected.replace(" or ", ", "),
                    "type": "type_error.enum",
                    "ctx": {"enum_values": re.findall(r"'([^']*)'", expected)},
                }
            )
        elif kind == "value_error":
            prefix = "Value error, "
            if msg.startswith(prefix):
                msg = msg[len(prefix):]
            translated.append({"loc": loc, "msg": msg, "type": "value_error"})
        else:
            item = {"loc": loc, "msg": msg, "type": kind}
            safe_ctx = {}
            for key, value in ctx.items():
                try:
                    json.dumps(value)
                except TypeError:
                    continue
                safe_ctx[key] = value
            if safe_ctx:
                item["ctx"] = safe_ctx
            translated.append(item)
    return translated


_TYPE_ERRORS = {
    "string_type",
    "list_type",
    "dict_type",
    "int_type",
    "float_type",
    "bool_type",
    "bytes_type",
}


def _failed_fields(errors) -> set:
    """Fields that failed on this model, not inside a nested value.

    ``('is_secure',)`` is a direct failure, so the ``mode="after"`` validator
    still runs. ``('payload', 0, '__root__')`` means the list was present and a
    child already failed. Dropping that list makes the parent validator report
    an empty payload as well.
    """
    failed = set()
    for err in errors:
        loc = err.get("loc") or ()
        if len(loc) == 1 and isinstance(loc[0], str) and loc[0] != "__root__":
            failed.add(loc[0])
    return failed


def _has_empty_value_error(errors) -> bool:
    return any(
        err.get("type") == "value_error" and tuple(err.get("loc") or ()) == ()
        for err in errors
    )


def _rootify(errors) -> list:
    prepared = []
    for err in errors:
        loc = tuple(err.get("loc") or ())
        if err.get("type") == "value_error" and loc == ():
            loc = ("__root__",)
        item = {"type": err["type"], "loc": loc, "input": err.get("input")}
        if err.get("ctx"):
            item["ctx"] = err["ctx"]
        prepared.append(item)
    return prepared


def _construct_partial(cls, values: dict, failed: set):
    data = {}
    for name, field in cls.model_fields.items():
        if name in failed:
            data[name] = None
        elif name in values:
            data[name] = values[name]
        elif not field.is_required():
            if field.default_factory is not None:
                data[name] = field.default_factory()
            else:
                default = field.default
                if isinstance(default, list):
                    default = list(default)
                elif isinstance(default, dict):
                    default = dict(default)
                elif isinstance(default, set):
                    default = set(default)
                data[name] = default
    return cls.model_construct(**data)


def _rerun_after_validators(cls, values: dict, failed: set) -> list:
    try:
        instance = _construct_partial(cls, values, failed)
    except Exception:
        return []
    extra = []
    decorators = getattr(cls, "__pydantic_decorators__", None)
    validators = getattr(decorators, "model_validators", {}) if decorators else {}
    for decorator in validators.values():
        if getattr(getattr(decorator, "info", None), "mode", None) != "after":
            continue
        try:
            decorator.func(instance)
        except ValueError as exc:
            extra.append(
                {
                    "type": "value_error",
                    "loc": ("__root__",),
                    "input": values,
                    "ctx": {"error": exc},
                }
            )
        except Exception:
            continue
    return extra
