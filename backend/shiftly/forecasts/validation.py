"""Fail-closed validation for untrusted model output."""
from datetime import date,timedelta


def analysis(value, source, as_of):
    if not isinstance(value,dict) or set(value)!={'summary','trends','recommendations','risks','limitations'}:
        raise ValueError('Invalid forecast response.')
    if (not isinstance(value['summary'],str) or not value['summary'].strip()
        or len(value['summary'])>4000): raise ValueError('Invalid forecast response.')
    for key in ('trends','risks','limitations'):
        if (not isinstance(value[key],list) or len(value[key])>20
            or any(not isinstance(x,str) or not x.strip() or len(x)>500 for x in value[key])):
            raise ValueError('Invalid forecast response.')
    recipes={r['id']:r['name'] for r in source['recipes'] if r.get('active') is True}; allowed={(date.fromisoformat(as_of)+timedelta(days=n)).isoformat() for n in (1,2,3)}
    if not isinstance(value['recommendations'],list) or len(value['recommendations'])>30: raise ValueError('Invalid forecast response.')
    recommendations=[]
    seen=set()
    for item in value['recommendations']:
        if (not isinstance(item,dict) or set(item)!={'recipeId','name','day','batches','rationale'}
            or item['recipeId'] not in recipes or item['name']!=recipes[item['recipeId']]
            or item['day'] not in allowed or type(item['batches']) is not int or not 0<=item['batches']<=1000
            or not isinstance(item['rationale'],str) or not item['rationale'].strip() or len(item['rationale'])>1000
            or (item['recipeId'],item['day']) in seen):
            raise ValueError('Invalid forecast response.')
        seen.add((item['recipeId'],item['day']))
        recommendations.append({**item,'rationale':item['rationale'].strip()})
    return {'summary':value['summary'].strip(),
            'trends':[x.strip() for x in value['trends']],
            'recommendations':recommendations,
            'risks':[x.strip() for x in value['risks']],
            'limitations':[x.strip() for x in value['limitations']]}
