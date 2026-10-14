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
        if 'barcodeType' in fields:
            from .barcodes import identity
            data['sku'], data['barcodeAliases'] = identity(sku, fields['barcodeType'])
            data['barcodeType'] = fields['barcodeType']
    elif 'barcodeType' in fields:
        invalid('Barcode type can only be supplied when creating a product from a scan.')
    elif 'baseUnit' in fields:
        invalid('The base unit cannot be edited. Create a new product for a different stock unit.')
    if 'containerAmount' in fields:
        # Validation depends on the stored unit for edits, within the transaction.
        data['containerAmount'] = fields['containerAmount']
    if 'containerUnit' in fields:
        if fields.get('containerAmount') is None:
            invalid('A container unit requires a container amount.')
        data['containerUnit'] = fields['containerUnit']
    return data


def version(value):
    if type(value) is not int or not 1 <= value <= 2147483647:
        invalid('A current record version is required.')
    return value


def package_fields(fields):
    kind = fields.get('kind')
    if kind not in ('container', 'box', 'case'):
        invalid('Choose container, box or case as the package kind.')
    data = {'name': text(fields.get('name'), 'Package name', 120), 'kind': kind}
    contained = fields.get('containedPackageId')
    count = fields.get('containedCount')
    if (contained is None) != (count is None):
        invalid('A contained package and count must be supplied together.')
    if contained is not None:
        if kind != 'case':
            invalid('Only a case can contain another package option.')
        if type(count) is not int or not 1 <= count <= 1000000:
            invalid('Contained count must be a whole number from 1 to 1000000.')
        data.update(containedPackageId=identifier(contained), containedCount=count)
        if fields.get('amount') is not None:
            invalid('A contained case amount is computed from its package and count.')
        if 'amountUnit' in fields:
            invalid('A contained case amount unit is computed from its package.')
    else:
        data.update(containedPackageId=None, containedCount=None, amount=fields.get('amount'))
        if 'amountUnit' in fields:
            if fields.get('amount') is None:
                invalid('An amount unit requires an amount.')
            data['amountUnit'] = fields['amountUnit']
    barcode = fields.get('barcode')
    barcode_type = fields.get('barcodeType')
    if barcode is not None:
        barcode = text(barcode, 'Barcode', 64)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,63}', barcode):
            invalid('Barcode must use the supported identifier characters.')
        if barcode_type is not None:
            from .barcodes import identity
            barcode, aliases = identity(barcode, barcode_type)
        else:
            aliases = (barcode,)
        data.update(barcode=barcode, barcodeAliases=aliases)
    elif barcode_type is not None:
        invalid('Barcode type requires a barcode.')
    return data


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
