"""Bounded image and model-output validation for private invoice proposals."""
import base64, binascii, io, re, unicodedata
from decimal import Decimal, InvalidOperation

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_DIMENSION = 4096
MAX_LINES = 60
UNITS = {'', 'kg', 'g', 'lb', 'each', 'package'}
QUANTITY = re.compile(r'^\d{1,9}(?:\.\d{1,9})?$')


def sanitized_image(value):
    if not isinstance(value, str) or len(value) > ((MAX_IMAGE_BYTES + 2) // 3) * 4 + 16:
        raise ValueError('Invoice photo is invalid or too large.')
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError('Invoice photo is invalid.') from error
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError('Invoice photo is invalid or too large.')
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in {'JPEG', 'PNG'} or source.width * source.height > MAX_PIXELS:
                raise ValueError('Invoice photo must be a JPEG or PNG up to 20 megapixels.')
            source.load()
            image = ImageOps.exif_transpose(source).convert('RGB')
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as error:
        raise ValueError('Invoice photo is invalid.') from error
    if max(image.size) > MAX_DIMENSION:
        image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, 'JPEG', quality=85, optimize=True, progressive=True)
    data = output.getvalue()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError('Invoice photo is too detailed. Crop it and try again.')
    return data


def _text(value, limit, *, empty=True):
    if (
        not isinstance(value, str)
        or len(value) > limit
        or any(unicodedata.category(character).startswith('C') for character in value)
        or (not empty and not value.strip())
    ):
        raise ValueError('Invalid invoice photo response.')
    return value.strip()


def proposal(value):
    if not isinstance(value, dict) or set(value) != {'supplier', 'invoiceNumber', 'lines'}:
        raise ValueError('Invalid invoice photo response.')
    supplier = _text(value['supplier'], 120)
    number = _text(value['invoiceNumber'], 80)
    if not isinstance(value['lines'], list) or len(value['lines']) > MAX_LINES:
        raise ValueError('Invalid invoice photo response.')
    lines = []
    for raw in value['lines']:
        if not isinstance(raw, dict) or set(raw) != {'description', 'sku', 'quantity', 'unit'}:
            raise ValueError('Invalid invoice photo response.')
        description, sku = _text(raw['description'], 160, empty=False), _text(raw['sku'], 64)
        unit = _text(raw['unit'], 24)
        quantity = raw['quantity']
        if quantity is not None:
            quantity = _text(quantity, 40, empty=False)
            if not QUANTITY.fullmatch(quantity):
                raise ValueError('Invalid invoice photo response.')
            try:
                parsed = Decimal(quantity)
            except InvalidOperation as error:
                raise ValueError('Invalid invoice photo response.') from error
            if not parsed.is_finite() or parsed < 0:
                raise ValueError('Invalid invoice photo response.')
            quantity = format(parsed, 'f')
        if unit not in UNITS:
            unit = ''
        lines.append({'description': description, 'sku': sku, 'quantity': quantity, 'unit': unit})
    return {'supplier': supplier, 'invoiceNumber': number, 'lines': lines}
