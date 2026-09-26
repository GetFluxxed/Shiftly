"""Exact, bounded count measurements. A missing observation is not zero."""
from datetime import date
from decimal import Decimal
import re

from ..validation import invalid
from ..quantities import decimal_text

MAX_QUANTITY = Decimal('999999999999999.999999999')


def business_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        invalid('Choose the count date as YYYY-MM-DD.')
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        invalid('Choose a valid count date.')


def number(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,9}(?:\.\d{1,6})?', value):
        invalid(f'{label} must be a nonnegative number with up to six decimal places.')
    return Decimal(value)


def mass_or_items(value, unit, base):
    if unit == base:
        if base == 'each' and value != value.to_integral_value():
            invalid('Individual items must be whole numbers.')
        return value
    if {unit, base} == {'g', 'kg'}:
        return value / 1000 if unit == 'g' else value * 1000
    invalid('Choose the product unit, or grams/kilograms for a weight.')


def measurement(value, product):
    if not isinstance(value, dict):
        invalid('Enter a count or confirm none remaining.')
    mode, base = value.get('mode'), product['base_unit']
    if mode == 'total' and set(value) == {'mode', 'amount', 'unit'}:
        quantity = mass_or_items(number(value['amount'], 'Total'), value['unit'], base)
        entry = {'mode': mode, 'amount': decimal_text(number(value['amount'], 'Total')), 'unit': value['unit']}
    elif mode == 'containers' and set(value) == {'mode', 'fullContainers', 'partialAmount', 'partialUnit'}:
        full = value['fullContainers']
        if type(full) is not int or not 0 <= full <= 1_000_000:
            invalid('Full containers must be a whole number between zero and one million.')
        if product['container_amount'] is None:
            invalid('This product has no full-container reference. Enter its measured total instead.')
        partial = number(value['partialAmount'], 'Net partial amount')
        quantity = full * product['container_amount'] + mass_or_items(partial, value['partialUnit'], base)
        entry = {'mode': mode, 'fullContainers': full, 'partialAmount': decimal_text(partial), 'partialUnit': value['partialUnit']}
    else:
        invalid('Choose a total measurement or full containers plus net partial amount.')
    if quantity > MAX_QUANTITY:
        invalid('The counted quantity is too large.')
    return quantity, entry


def bounded_total(quantity):
    if quantity > MAX_QUANTITY:
        invalid('The combined quantity across shelves is too large.')
