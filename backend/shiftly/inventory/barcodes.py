"""Strict barcode normalization for catalog identity; never infers products."""
import re

from .validation import invalid, text


BARCODE_TYPES = frozenset(('ean13', 'ean8', 'upc_a', 'upc_e', 'code128', 'code39', 'code93', 'itf14', 'codabar'))
# Expo's iOS paths do not consistently return Expo's public short names.
# Keep this exact and closed: these are AVFoundation ObjectType raw values and
# Vision VNBarcodeSymbology raw values for the retail types Shiftly accepts.
BARCODE_TYPE_ALIASES = {
    **{barcode_type: barcode_type for barcode_type in BARCODE_TYPES},
    'org.gs1.EAN-13': 'ean13',
    'org.gs1.EAN-8': 'ean8',
    'org.gs1.UPC-E': 'upc_e',
    'org.iso.Code39': 'code39',
    'com.intermec.Code93': 'code93',
    'org.iso.Code128': 'code128',
    'org.gs1.ITF14': 'itf14',
    'Codabar': 'codabar',
    'VNBarcodeSymbologyEAN13': 'ean13',
    'VNBarcodeSymbologyCode39': 'code39',
}
SKU_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,63}')


def _valid_gtin(value):
    digits = [int(digit) for digit in value]
    expected = (10 - sum(digit * (3 if offset % 2 == 0 else 1)
                         for offset, digit in enumerate(reversed(digits[:-1]))) % 10) % 10
    return expected == digits[-1]


def _gtin_aliases(canonical):
    """Return valid GTIN-8/12/13/14 forms reachable by zero padding only."""
    padded = canonical.zfill(14)
    aliases = []
    for length in (8, 12, 13, 14):
        prefix, candidate = padded[:-length], padded[-length:]
        if (not prefix or set(prefix) == {'0'}) and _valid_gtin(candidate):
            aliases.append(candidate)
    return tuple(dict.fromkeys((canonical, *aliases)))


def identity(value, barcode_type=None):
    """Return canonical SKU plus exact aliases that represent the same scan."""
    value = text(value, 'SKU', 64)
    if not SKU_PATTERN.fullmatch(value):
        invalid('SKU must start with a letter or number and use only letters, numbers, dot, slash, dash or underscore.')
    if barcode_type is None:
        return value, (value,)
    if not isinstance(barcode_type, str) or barcode_type not in BARCODE_TYPE_ALIASES:
        invalid('Choose a supported barcode type.')
    barcode_type = BARCODE_TYPE_ALIASES[barcode_type]

    if barcode_type == 'upc_a':
        if len(value) == 13 and value.startswith('0'):
            raw = value[1:]
        elif len(value) == 12:
            raw = value
        else:
            invalid('UPC-A must contain 12 digits.')
        if not raw.isascii() or not raw.isdigit():
            invalid('UPC-A must contain 12 digits.')
        if not _valid_gtin(raw):
            invalid('UPC-A check digit is invalid.')
        canonical = '0' + raw
        return canonical, _gtin_aliases(canonical)

    # Expo iOS reports EAN-13 but strips a leading zero from its data. A valid
    # 12-digit result is therefore the UPC-A representation of the same GTIN.
    if barcode_type == 'ean13' and len(value) == 12:
        if not value.isascii() or not value.isdigit():
            invalid('EAN-13 must contain 13 digits, or a valid 12-digit UPC-A value from iOS.')
        if not _valid_gtin(value):
            invalid('EAN-13 check digit is invalid.')
        canonical = '0' + value
        return canonical, _gtin_aliases(canonical)

    lengths = {'ean13': 13, 'ean8': 8, 'upc_e': 8, 'itf14': 14}
    if barcode_type in lengths:
        length = lengths[barcode_type]
        label = {'ean13': 'EAN-13', 'ean8': 'EAN-8', 'upc_e': 'UPC-E', 'itf14': 'ITF-14'}[barcode_type]
        if len(value) != length or not value.isascii() or not value.isdigit():
            invalid(f'{label} must contain {length} digits.')
        if barcode_type != 'upc_e' and not _valid_gtin(value):
            invalid(f'{label} check digit is invalid.')
        return value, _gtin_aliases(value) if barcode_type in ('ean13', 'ean8', 'itf14') else (value,)

    return value, (value,)
