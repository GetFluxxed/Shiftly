from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import unicodedata

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.inventory.validation import identifier, text, version

UNITS = ('each', 'g', 'kg')
MAX_QUANTITY = Decimal('999999999999999.999999999')


def invalid(message):
    raise IdentityError('invalid', message)


def decimal_amount(value, label, *, allow_zero=False):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,15}(?:\.[0-9]{1,9})?', value.strip()):
        invalid(f'{label} must be decimal text with at most nine decimal places.')
    try:
        result = Decimal(value.strip())
    except InvalidOperation:
        invalid(f'{label} is invalid.')
    if result < 0 or (not allow_zero and result == 0) or result > MAX_QUANTITY:
        invalid(f'{label} must be greater than zero and within the supported range.')
    return result


def exact(value, label='Calculated quantity'):
    value = value.normalize() if value else Decimal(0)
    if value > MAX_QUANTITY or value < 0 or value.as_tuple().exponent < -9:
        invalid(f'{label} cannot be represented exactly with at most nine decimal places.')
    return value


def unit(value, label='Unit'):
    if value not in UNITS:
        invalid(f'{label} must be each, g, or kg.')
    return value


def yield_unit(value):
    return text(value, 'Yield unit', 40)


def convert(value, source, target):
    unit(source); unit(target)
    if source == target:
        return exact(value)
    if {source, target} != {'g', 'kg'}:
        invalid('Ingredient units must match the product base unit, except for exact g/kg conversion.')
    return exact(value * Decimal(1000) if source == 'kg' else value / Decimal(1000))


def recipe_input(fields):
    if not isinstance(fields, dict):
        invalid('Recipe fields are required.')
    ingredients = fields.get('ingredients')
    if not isinstance(ingredients, list) or not 1 <= len(ingredients) <= 50:
        invalid('A recipe must contain 1 to 50 ingredients.')
    seen = set(); parsed = []
    for item in ingredients:
        if not isinstance(item, dict): invalid('Each ingredient must be an object.')
        product_id = identifier(item.get('productId'))
        if product_id in seen: invalid('Each product may appear only once in a recipe revision.')
        seen.add(product_id)
        parsed.append({'productId': product_id, 'amount': decimal_amount(item.get('amount'),'Ingredient amount'),
                       'unit': unit(item.get('unit'),'Ingredient unit')})
    instructions = fields.get('instructions')
    if instructions is None: instructions = ''
    if not isinstance(instructions,str) or len(instructions)>20_000 or any(unicodedata.category(c).startswith('C') and c not in '\n\r\t' for c in instructions):
        invalid('Instructions must be text of at most 20,000 characters.')
    return {'name':text(fields.get('name'),'Recipe name',160),
            'yieldAmount':decimal_amount(fields.get('yieldAmount'),'Yield amount'),
            'yieldUnit':yield_unit(fields.get('yieldUnit')), 'instructions':instructions.strip(),
            'ingredients':parsed}


def business_date(value):
    if not isinstance(value,str): invalid('Business date is required.')
    try: parsed=date.fromisoformat(value)
    except ValueError: invalid('Business date must use YYYY-MM-DD.')
    if parsed.isoformat()!=value: invalid('Business date must use YYYY-MM-DD.')
    return parsed


def entries(value):
    if not isinstance(value,list) or not 1 <= len(value) <= 100: invalid('Provide 1 to 100 production entries.')
    result=[]
    for item in value:
        if not isinstance(item,dict): invalid('Each production entry must be an object.')
        batches=item.get('batches')
        if type(batches) is not int or not 1 <= batches <= 1000: invalid('Batches must be a whole number from 1 to 1000.')
        result.append({'recipeId':identifier(item.get('recipeId')),'revisionId':identifier(item.get('revisionId')),'batches':batches})
    return result


def normalized(value):
    def render(item):
        if isinstance(item,Decimal): return format(item,'f')
        if isinstance(item,date): return item.isoformat()
        if isinstance(item,dict): return {k:render(v) for k,v in item.items()}
        if isinstance(item,list): return [render(v) for v in item]
        return item
    return render(value)


def fingerprint(operation, payload):
    return hashlib.sha256(json.dumps([operation,normalized(payload)],sort_keys=True,separators=(',',':')).encode()).hexdigest()
