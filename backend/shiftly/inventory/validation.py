"""Bounded inventory inputs; SKU normalization is also enforced by PostgreSQL."""
import base64
import json
import re
import unicodedata
from uuid import UUID

from backend.shiftly.identity.contracts import IdentityError

UNITS = ('each', 'g', 'kg')


def invalid(message):
    raise IdentityError('invalid', message)


def identifier(value):
    if not isinstance(value, str):
        invalid('A valid identifier is required.')
    try:
        parsed = UUID(value)
    except ValueError:
        invalid('A valid identifier is required.')
    if str(parsed) != value:
        invalid('A canonical identifier is required.')
    return value


def text(value, label, maximum):
    if not isinstance(value, str) or any(unicodedata.category(c).startswith('C') for c in value):
        invalid(f'{label} must be text without control characters.')
    value = unicodedata.normalize('NFKC', value).strip()
    if not 1 <= len(value) <= maximum:
        invalid(f'{label} must contain 1 to {maximum} characters.')
    return value


def product_fields(fields, *, creating=False):
    sku = text(fields.get('sku'), 'SKU', 64)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,63}', sku):
        invalid('SKU must start with a letter or number and use only letters, numbers, dot, slash, dash or underscore.')
    data = {'name': text(fields.get('name'), 'Product name', 160), 'sku': sku}
    if creating:
        if fields.get('baseUnit') not in UNITS:
            invalid('Choose an explicit base unit.')
        data['baseUnit'] = fields['baseUnit']
    elif 'baseUnit' in fields:
        invalid('The base unit cannot be edited. Create a new product for a different stock unit.')
    if 'containerAmount' in fields:
        # Validation depends on the stored unit for edits, within the transaction.
        data['containerAmount'] = fields['containerAmount']
    return data


def version(value):
    if type(value) is not int or not 1 <= value <= 2147483647:
        invalid('A current record version is required.')
    return value


def page(query, after):
    if not isinstance(query, str) or len(query) > 160 or any(unicodedata.category(c).startswith('C') for c in query):
        invalid('Search must be text of at most 160 characters.')
    return unicodedata.normalize('NFKC', query).strip(), identifier(after) if after else None


def current(record, expected):
    if record['version'] != version(expected):
        raise IdentityError('conflict', 'This record changed. Reload the latest version before saving.', reason='stale_record')


def product_cursor(value):
    if not value:
        return None
    if not isinstance(value, str) or len(value) > 1200 or not re.fullmatch(r'p1\.[A-Za-z0-9_-]+', value):
        invalid('Reload the catalog to start a fresh alphabetical page.')
    try:
        encoded = value[3:]
        fields = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
        if not isinstance(fields, list) or len(fields) != 2 or not isinstance(fields[0], str) or len(fields[0]) > 320:
            raise ValueError()
        if any(unicodedata.category(c).startswith('C') for c in fields[0]):
            raise ValueError()
        return fields[0], identifier(fields[1])
    except (ValueError, UnicodeError):
        invalid('Reload the catalog to start a fresh alphabetical page.')


def encode_product_cursor(name, product_id):
    data = json.dumps([name, str(product_id)], ensure_ascii=False, separators=(',', ':')).encode()
    return 'p1.' + base64.urlsafe_b64encode(data).decode().rstrip('=')
