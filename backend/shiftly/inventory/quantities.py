"""Exact quantities shared by package configuration and future measured counts.

A partial belongs to the same product as full containers. Convert its net mass
into that product's fixed base unit; never infer tare or a mass/volume conversion.
"""
from decimal import Decimal, ROUND_HALF_UP, localcontext
import re

from .validation import invalid

MAX_AMOUNT = Decimal('999999999.999999999')
LB_TO_KG = Decimal('0.45359237')
NINE_PLACES = Decimal('0.000000001')


def amount(value, *, label='Container amount', places=9):
    if not isinstance(value, str) or not re.fullmatch(
            rf'[0-9]{{1,9}}(?:\.[0-9]{{1,{places}}})?', value.strip()):
        invalid(f'{label} must be decimal text with up to {places} decimal places.')
    result = Decimal(value.strip())
    if not 0 < result <= MAX_AMOUNT:
        invalid(f'{label} must be greater than zero and no more than {MAX_AMOUNT}.')
    return result


def package_amount(value, base_unit, unit=None):
    """Return canonical base-unit amount plus optional original label metadata."""
    if value is None:
        if unit is not None:
            invalid('An amount unit requires an amount.')
        return None, None, None
    source_unit = base_unit if unit is None else unit
    if source_unit not in ('each', 'g', 'kg', 'lb'):
        invalid('Choose items, grams, kilograms or pounds for the package amount.')
    if base_unit == 'each':
        if source_unit != 'each':
            invalid('Item packages must use items.')
        source = amount(value, places=9)
        if source != source.to_integral_value():
            invalid('A full container must hold a whole number of items.')
        canonical = source
    elif base_unit in ('g', 'kg'):
        if source_unit == 'each':
            invalid('Mass packages must use grams, kilograms or pounds.')
        source = amount(value, places=6 if source_unit == 'lb' else 9)
        with localcontext() as context:
            context.prec = 50
            kilograms = source * LB_TO_KG if source_unit == 'lb' else source / Decimal(1000) if source_unit == 'g' else source
            canonical = kilograms * Decimal(1000) if base_unit == 'g' else kilograms
            canonical = canonical.quantize(NINE_PLACES, rounding=ROUND_HALF_UP)
        if not 0 < canonical <= MAX_AMOUNT:
            invalid(f'Container amount must be greater than zero and no more than {MAX_AMOUNT}.')
    else:
        invalid('Container amounts support items, grams and kilograms.')
    return decimal_text(canonical), (decimal_text(source) if unit is not None else None), (source_unit if unit is not None else None)


def decimal_text(value):
    result = format(value, 'f')
    return result.rstrip('0').rstrip('.') if '.' in result else result


def convert_mass(value, from_unit, to_unit):
    """Preserve exact mass, including precision gained when converting g to kg."""
    if from_unit not in ('g', 'kg') or to_unit not in ('g', 'kg'):
        invalid('Mass measurements must use grams or kilograms.')
    quantity = amount(value, label='Net weight')
    factor = Decimal(1000)
    if from_unit != to_unit:
        quantity = quantity * factor if from_unit == 'kg' else quantity / factor
    return quantity


def container_amount(value, base_unit):
    return package_amount(value, base_unit)[0]
