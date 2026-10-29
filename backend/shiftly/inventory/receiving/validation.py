"""Strict validation for reviewed invoice drafts and incoming previews."""
import base64
import binascii
import json
import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from backend.shiftly.identity.contracts import IdentityError

MAX_LINES = 60
UNITS = {'', 'kg', 'g', 'lb', 'each', 'package'}
MAX_QUANTITY = Decimal('999999999999999.999999999')
DECIMAL = re.compile(r'[0-9]{1,15}(?:\.[0-9]{1,9})?')


def invalid(message='Check the invoice fields and try again.'):
    raise IdentityError('invalid', message, reason='validation_failed')


def identifier(value, message='This identifier is invalid.'):
    if not isinstance(value, str):
        invalid(message)
    try:
        return str(UUID(value))
    except (ValueError, AttributeError):
        invalid(message)


def store_id(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        invalid('Select the store again before saving this invoice.')
    return value


def text(value, maximum, *, required=False, label='This value'):
    if not isinstance(value, str):
        invalid(f'{label} is invalid.')
    value = value.strip()
    if any(unicodedata.category(char).startswith('C') for char in value):
        invalid(f'{label} is invalid.')
    if (required and not value) or len(value) > maximum:
        invalid(f'{label} is invalid.')
    return value


def quantity(value, *, matched=False):
    if value is None:
        if matched:
            invalid('Matched invoice lines need a quantity.')
        return None
    if not isinstance(value, str) or not DECIMAL.fullmatch(value):
        invalid('Enter the quantity as a decimal number.')
    try:
        number = Decimal(value)
    except InvalidOperation:
        invalid('Enter the quantity as a decimal number.')
    if not number.is_finite() or number < 0 or number > MAX_QUANTITY:
        invalid('The invoice quantity is outside the supported range.')
    if matched and number <= 0:
        invalid('Matched invoice lines need a positive quantity.')
    return number


def version(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        invalid('Reload this invoice before saving it.')
    return value


def line(value):
    if not isinstance(value, dict):
        invalid('Each invoice line must be an object.')
    product_id = identifier(value['productId']) if value.get('productId') is not None else None
    package_id = identifier(value['packageId']) if value.get('packageId') is not None else None
    if package_id and not product_id:
        invalid('A package must belong to a matched product.')
    unit = value.get('unit', '')
    if not isinstance(unit, str) or unit not in UNITS:
        invalid('Choose a supported invoice unit.')
    if product_id and not unit:
        invalid('Choose a unit for each matched invoice line.')
    if package_id and unit != 'package':
        invalid('Package matches must use the package unit.')
    if not package_id and unit == 'package':
        invalid('Choose a package before using the package unit.')
    result = {
        'id': identifier(value.get('id')),
        'description': text(value.get('description'), 160, required=True, label='Line description'),
        'sku': text(value.get('sku', ''), 64, label='SKU'),
        'productId': product_id,
        'packageId': package_id,
        'quantity': quantity(value.get('quantity'), matched=bool(product_id)),
        'unit': unit,
        'received': value.get('received', False),
    }
    if not isinstance(result['received'], bool):
        invalid('Received must be checked or unchecked.')
    return result


def draft_fields(fields, *, editing=False):
    if not isinstance(fields, dict):
        invalid()
    result = {
        'requestId': identifier(fields.get('requestId')),
        'expectedStoreId': store_id(fields.get('expectedStoreId')),
        'supplier': text(fields.get('supplier', ''), 120, label='Supplier'),
        'invoiceNumber': text(fields.get('invoiceNumber', ''), 80, label='Invoice number'),
    }
    if editing:
        result['version'] = version(fields.get('version'))
    values = fields.get('lines', [])
    if not isinstance(values, list) or len(values) > MAX_LINES:
        invalid(f'An invoice can have at most {MAX_LINES} lines.')
    result['lines'] = [line(item) for item in values]
    ids = [item['id'] for item in result['lines']]
    if len(ids) != len(set(ids)):
        invalid('Each invoice line must have a different identifier.')
    return result


def action_fields(fields):
    if not isinstance(fields, dict):
        invalid()
    return {'requestId': identifier(fields.get('requestId')),
            'expectedStoreId': store_id(fields.get('expectedStoreId')),
            'version': version(fields.get('version'))}


def query(value):
    return text(value or '', 160, label='Search')


def encode_cursor(updated_at, item_id):
    raw = json.dumps([updated_at.isoformat(), str(item_id)], separators=(',', ':')).encode()
    return 'i1.' + base64.urlsafe_b64encode(raw).decode().rstrip('=')


def decode_cursor(value):
    if value is None:
        return None
    try:
        if not isinstance(value, str) or len(value) > 1024:
            raise ValueError()
        prefix, encoded = value.split('.', 1)
        raw = base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True)
        fields = json.loads(raw)
        if prefix != 'i1' or not isinstance(fields, list) or len(fields) != 2:
            raise ValueError()
        timestamp = datetime.fromisoformat(fields[0])
        if timestamp.tzinfo is None:
            raise ValueError()
        identifier(fields[1])
        return timestamp.isoformat(), fields[1]
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError, binascii.Error):
        invalid('Reload invoices to start a fresh page.')


def encode_product_cursor(name, product_id):
    raw = json.dumps([name, str(product_id)], ensure_ascii=False, separators=(',', ':')).encode()
    return 'r1.' + base64.urlsafe_b64encode(raw).decode().rstrip('=')


def decode_product_cursor(value):
    if value is None:
        return None
    try:
        if not isinstance(value, str) or len(value) > 1024:
            raise ValueError()
        prefix, encoded = value.split('.', 1)
        raw = base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True)
        fields = json.loads(raw)
        if prefix != 'r1' or not isinstance(fields, list) or len(fields) != 2 or not isinstance(fields[0], str) or len(fields[0]) > 320:
            raise ValueError()
        return fields[0], identifier(fields[1])
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError, binascii.Error):
        invalid('Reload incoming inventory to start a fresh page.')
