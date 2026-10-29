from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import unicodedata

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.inventory.validation import identifier, text, version

UNITS = ('each', 'g', 'kg')
SECTIONS = ('base', 'variegato')
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


def ingredient_name_key(value):
    return unicodedata.normalize('NFKC',value).strip().casefold()


def ingredient_section(value):
    if value not in SECTIONS:
        invalid('Ingredient section must be base or variegato.')
    return value


def recipe_input(fields, *, allow_omitted_references=False):
    if not isinstance(fields, dict):
        invalid('Recipe fields are required.')
    ingredients = fields.get('ingredients')
    if not isinstance(ingredients, list) or len(ingredients) > 50:
        invalid('Tracked ingredients must be an array of at most 50 items.')
    seen = set(); parsed = []; sections_complete = True
    for item in ingredients:
        if not isinstance(item, dict): invalid('Each ingredient must be an object.')
        product_id = identifier(item.get('productId'))
        sections_complete = sections_complete and 'section' in item
        section = ingredient_section(item.get('section','base'))
        if (product_id,section) in seen: invalid('Each product may appear only once in each recipe section.')
        seen.add((product_id,section))
        parsed.append({'productId': product_id, 'amount': decimal_amount(item.get('amount'),'Ingredient amount'),
                       'unit': unit(item.get('unit'),'Ingredient unit'),'section':section})
    if 'referenceIngredients' not in fields and allow_omitted_references:
        parsed_references = None
    else:
        references = fields.get('referenceIngredients', [])
        if not isinstance(references, list) or len(references) > 50:
            invalid('Reference ingredients must be an array of at most 50 items.')
        reference_names = set(); parsed_references = []
        for item in references:
            if not isinstance(item, dict): invalid('Each reference ingredient must be an object.')
            if set(item) not in ({'name','amount','unit'},{'name','amount','unit','section'}):
                invalid('Each reference ingredient must contain only name, amount, unit, and optional section.')
            name = text(item.get('name'),'Reference ingredient name',160)
            sections_complete = sections_complete and 'section' in item
            section = ingredient_section(item.get('section','base'))
            name_key = (ingredient_name_key(name),section)
            if name_key in reference_names:
                invalid('Each reference ingredient name may appear only once in each recipe section.')
            reference_names.add(name_key)
            amount = decimal_amount(item.get('amount'),'Reference ingredient amount')
            item_unit = unit(item.get('unit'),'Reference ingredient unit')
            if item_unit == 'each' and amount != amount.to_integral_value():
                invalid('Reference ingredient amounts in each must be whole numbers.')
            parsed_references.append({'name':name,'amount':amount,'unit':item_unit,'section':section})
        if not 1 <= len(parsed)+len(parsed_references) <= 50:
            invalid('A recipe must contain 1 to 50 tracked and reference ingredients in total.')
    instructions = fields.get('instructions')
    if instructions is None: instructions = ''
    if not isinstance(instructions,str) or len(instructions)>20_000 or any(unicodedata.category(c).startswith('C') and c not in '\n\r\t' for c in instructions):
        invalid('Instructions must be text of at most 20,000 characters.')
    return {'name':text(fields.get('name'),'Recipe name',160),
            'yieldAmount':decimal_amount(fields.get('yieldAmount'),'Yield amount'),
            'yieldUnit':yield_unit(fields.get('yieldUnit')), 'instructions':instructions.strip(),
            'ingredients':parsed, 'referenceIngredients':parsed_references,
            'ingredientSectionsComplete':sections_complete}


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
