"""Exact quantities shared by package configuration and future measured counts.

A partial belongs to the same product as full containers. Convert its net mass
into that product's fixed base unit; never infer tare or a mass/volume conversion.
"""
from decimal import Decimal
import re

from .validation import invalid

MAX_AMOUNT = Decimal('999999999.999999')


def amount(value, *, label='Container amount'):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,9}(?:\.[0-9]{1,6})?', value.strip()):
        invalid(f'{label} must be decimal text with up to six decimal places.')
    result = Decimal(value.strip())
    if not 0 < result <= MAX_AMOUNT:
        invalid(f'{label} must be greater than zero and no more than {MAX_AMOUNT}.')
    return result


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
    if value is None:
        return None
    if base_unit not in ('each', 'g', 'kg'):
        invalid('Container amounts support items, grams and kilograms.')
    quantity = amount(value)
    if base_unit == 'each' and quantity != quantity.to_integral_value():
        invalid('A full container must hold a whole number of items.')
    return decimal_text(quantity)
