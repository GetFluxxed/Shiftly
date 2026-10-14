"""Bounded Responses API transport dedicated to forecast JSON."""
import json,ssl,urllib.error,urllib.request

try: import certifi
except ImportError: certifi=None

SCHEMA={'type':'object','additionalProperties':False,'required':['summary','trends','recommendations','risks','limitations'],
 'properties':{'summary':{'type':'string','maxLength':4000},'trends':{'type':'array','maxItems':20,'items':{'type':'string','maxLength':500}},
 'recommendations':{'type':'array','maxItems':30,'items':{'type':'object','additionalProperties':False,
   'required':['recipeId','name','day','batches','rationale'],'properties':{
   'recipeId':{'type':'string'},'name':{'type':'string'},'day':{'type':'string','pattern':'^\\d{4}-\\d{2}-\\d{2}$'},
   'batches':{'type':'integer','minimum':0,'maximum':1000},'rationale':{'type':'string','maxLength':1000}}}},
 'risks':{'type':'array','maxItems':20,'items':{'type':'string','maxLength':500}},
 'limitations':{'type':'array','maxItems':20,'items':{'type':'string','maxLength':500}}}}

class ForecastNotConfigured(RuntimeError):
    pass


def make_forecast_provider(settings):
    def provider(report,prompt):
        if not settings.openai_api_key: raise ForecastNotConfigured('Forecast generation is not configured.')
        if not isinstance(report.get('notes'),str) or len(report['notes'].encode())>80000:
            raise ValueError('Forecast input is invalid or too large.')
        request={'model':settings.openai_model,'store':False,
          'input':[{'role':'system','content':[{'type':'input_text','text':prompt}]},
                   {'role':'user','content':[{'type':'input_text','text':report['notes']}]}],
          'text':{'format':{'type':'json_schema','name':'production_forecast','strict':True,'schema':SCHEMA}},
          'max_output_tokens':1800}
        req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(request).encode(),
          headers={'Authorization':f'Bearer {settings.openai_api_key}','Content-Type':'application/json'},method='POST')
        context=ssl.create_default_context(cafile=certifi.where()) if certifi else ssl.create_default_context()
        try:
            with urllib.request.urlopen(req,timeout=30,context=context) as response:
                raw=response.read(80001)
                if len(raw)>80000: raise RuntimeError('Forecast response was too large.')
                payload=json.loads(raw)
        except (urllib.error.URLError,urllib.error.HTTPError) as error:
            raise RuntimeError('Forecast provider request failed.') from error
        if (not isinstance(payload,dict) or payload.get('status')!='completed'
            or payload.get('error') is not None or not isinstance(payload.get('output'),list)):
            raise RuntimeError('Forecast provider did not complete the response.')
        parts=[]
        for item in payload['output']:
            if not isinstance(item,dict): raise RuntimeError('Invalid forecast provider response.')
            if item.get('type')=='reasoning': continue
            if (item.get('type')!='message' or item.get('status') not in (None,'completed')
                or not isinstance(item.get('content'),list)):
                raise RuntimeError('Invalid forecast provider response.')
            for content in item['content']:
                if (not isinstance(content,dict) or content.get('type')!='output_text'
                    or not isinstance(content.get('text'),str)):
                    raise RuntimeError('Forecast provider returned no usable result.')
                parts.append(content['text'])
        if not parts: raise RuntimeError('Forecast provider returned no result.')
        return json.loads(''.join(parts))
    return provider
