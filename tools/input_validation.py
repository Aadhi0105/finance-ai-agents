"""Validate the actual advertised tool schema before any tool executes."""
import json
from jsonschema import Draft202012Validator


def validate_input(schema, value):
    try:
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, OverflowError):
        return 'arguments must be finite JSON values'
    errors = list(Draft202012Validator(schema).iter_errors(value))
    if errors:
        # Do not echo arbitrary argument values (they may contain sensitive text).
        error = errors[0]
        path = '.'.join(map(str, error.absolute_path)) or 'arguments'
        return f'{path}: violates {error.validator} constraint'
    return None
