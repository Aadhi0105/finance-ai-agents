"""Agent 4's bounded EUR input domain and exact monetary conversion.

Floats use their shortest decimal representation, never their binary expansion.
Factor arithmetic uses exact rationals; each extended amount rounds half-even once.
"""
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from datetime import date

MAX_CENTS = 2**63 - 1


def cents(value, field='cents'):
    if type(value) is not int or abs(value) > MAX_CENTS:
        raise ValueError(f'{field}: expected integer cents within signed BIGINT range')
    return value


def numeric(value, field='amount'):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal, Fraction)):
        raise ValueError(f'{field}: expected a finite decimal number, not a boolean')
    if isinstance(value, Fraction):
        result = value
    else:
        try:
            dec = Decimal(str(value))
        except InvalidOperation:
            raise ValueError(f'{field}: invalid decimal number') from None
        if not dec.is_finite() or abs(dec) > Decimal(MAX_CENTS) / 100 or dec.as_tuple().exponent < -12:
            raise ValueError(f'{field}: nonfinite, out-of-range or more than 12 decimal places')
        result = Fraction(dec)
    if abs(result) > Fraction(MAX_CENTS, 100):
        raise ValueError(f'{field}: amount out of range')
    return result


def money(value):
    return cents(round(numeric(value) * 100), 'rounded amount')


def name(value, field='name'):
    if not isinstance(value, str) or not value.strip() or value != value.strip() or '/' in value:
        raise ValueError(f'{field}: expected a nonempty trimmed name without /')
    return value


def metadata(value):
    """Optional provenance; omitted context means unverified legacy EUR input."""
    if not isinstance(value, dict):
        raise ValueError('context: expected an object')
    allowed = {'currency', 'monetary_unit', 'quantity_unit', 'entity', 'close_date', 'source_version'}
    if set(value) - allowed:
        raise ValueError('context: unsupported fields')
    if value.get('currency', 'EUR') != 'EUR' or value.get('monetary_unit', 'major') != 'major':
        raise ValueError('only EUR major-unit source amounts are supported')
    for key, val in value.items():
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f'context.{key}: expected a nonempty string')
    if 'close_date' in value:
        try:
            date.fromisoformat(value['close_date'])
        except ValueError:
            raise ValueError('context.close_date: expected ISO date') from None
    return dict(value)


def normalize_line(line):
    if not isinstance(line, dict):
        raise ValueError('line: expected an object')
    if set(line) - {'name', 'type', 'budget', 'actual', 'context'}:
        raise ValueError('line: unsupported fields; financial metadata belongs in context')
    name(line.get('name'))
    kind = line.get('type')
    if kind not in {'revenue', 'variable_cost', 'fixed_cost'}:
        raise ValueError('invalid line type: expected revenue / variable_cost / fixed_cost')
    if 'products' in line:
        raise ValueError('product baskets require decompose_multiproduct')
    context = metadata(line.get('context', {}))
    factor = 'price' if kind == 'revenue' else 'rate'
    sides = []
    for key in ('budget', 'actual'):
        side = line.get(key)
        if not isinstance(side, dict) or not side:
            raise ValueError(f'missing {key} amount for {line["name"]}')
        if set(side) == {'amount'}:
            sides.append({'amount': numeric(side['amount'], key + '.amount')})
        elif kind != 'fixed_cost' and set(side) == {factor, 'volume'}:
            parsed = {k: numeric(v, key + '.' + k) for k, v in side.items()}
            if any(v < 0 for v in parsed.values()):
                raise ValueError('unit factors and quantities must be nonnegative; use signed amount-only credits')
            sides.append(parsed)
        else:
            raise ValueError(f'{key}: conflicting or incomplete amount/unit representation')
    if set(sides[0]) != set(sides[1]):
        raise ValueError('budget and actual must use the same representation')
    return {**line, 'context': context, 'budget': sides[0], 'actual': sides[1]}
