"""Compatibility adapter for the supported browser host during FastAPI cutover.

All recipe and stock behavior stays in ProductionService. Dependencies come from
legacy composition, so the domain never imports the legacy server or its routes.
"""
from urllib.parse import urlparse, parse_qs

import psycopg

from backend.shiftly.core.http import ERROR_STATUS, same_origin
from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.production import ProductionService


def handle(handler, *, method, connect, accounts, token, parse_body):
    parsed=urlparse(handler.path)
    prefix='/api/production/'
    if not parsed.path.startswith(prefix): return False
    path=parsed.path[len(prefix):].split('/')
    query=parse_qs(parsed.query)
    service=ProductionService(connect,accounts)
    try:
        if method=='POST':
            same_origin(handler)
            fields=parse_body(handler,max_body=40_000)
        if path==['recipes']:
            result=(service.create_recipe(token,fields) if method=='POST' else
                    service.recipes(token,query=query.get('q',[''])[0],after=query.get('after',[None])[0]))
        elif len(path)==2 and path[0]=='recipes':
            result=service.edit_recipe(token,path[1],fields) if method=='POST' else service.recipe(token,path[1])
        elif path==['preview'] and method=='POST':
            result=service.preview(token,fields)
        elif path==['logs']:
            result=service.confirm(token,fields) if method=='POST' else service.logs(token,after=query.get('after',[None])[0])
        elif len(path)==2 and path[0]=='logs' and method=='GET':
            result=service.log(token,path[1])
        elif len(path)==3 and path[0]=='logs' and path[2]=='reverse' and method=='POST':
            result=service.reverse(token,path[1],fields)
        else:
            handler.send_json(404,{'error':'Not found.'}); return True
        handler.send_json(200,result)
    except IdentityError as error:
        handler.send_json(ERROR_STATUS.get(error.code,503),{'error':str(error),'errorCode':error.reason or error.code})
    except (ValueError,TypeError,UnicodeError):
        handler.send_json(400,{'error':'Invalid production request.','errorCode':'validation_failed'})
    except (psycopg.Error,RuntimeError):
        handler.send_json(503,{'error':'Production is temporarily unavailable.'})
    return True
