"""Native and cookie adapters for the shared production service."""
import psycopg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from backend.shiftly.core.dependencies import AppContext, get_app_context, named_account_token
from backend.shiftly.core.http import call, same_origin
from backend.shiftly.core.native import native_token, error_response, unavailable
from backend.shiftly.core.request import RequestBodyError, bounded_json
from backend.shiftly.identity.contracts import IdentityError

router=APIRouter(prefix='/api/mobile/production')
browser_router=APIRouter(prefix='/api/production')


async def dispatch(request,context,operation,*args,browser=False,**kwargs):
    try:
        token=named_account_token(request) if browser else native_token(request)
        if request.method=='POST':
            same_origin(request)
            fields=await bounded_json(request,max_body=40_000,invalid_message='Invalid production request.')
            return await call(operation,token,*args,fields)
        return await call(operation,token,*args,**kwargs)
    except IdentityError as error:return error_response(error)
    except (RequestBodyError,ValueError,TypeError,UnicodeError):
        return JSONResponse(status_code=400,content={'error':'Invalid production request.','errorCode':'validation_failed'})
    except (psycopg.Error,RuntimeError):return unavailable()


def add_routes(api,browser):
    @api.api_route('/recipes',methods=['GET','POST'])
    async def recipes(request:Request,context:AppContext=Depends(get_app_context)):
        service=context.services.production
        return await dispatch(request,context,service.create_recipe if request.method=='POST' else service.recipes,
                              browser=browser,query=request.query_params.get('q',''),after=request.query_params.get('after'))

    @api.api_route('/recipes/{recipe_id}',methods=['GET','POST'])
    async def recipe(recipe_id:str,request:Request,context:AppContext=Depends(get_app_context)):
        service=context.services.production
        return await dispatch(request,context,service.edit_recipe if request.method=='POST' else service.recipe,recipe_id,browser=browser)

    @api.post('/preview')
    async def preview(request:Request,context:AppContext=Depends(get_app_context)):
        return await dispatch(request,context,context.services.production.preview,browser=browser)

    @api.api_route('/logs',methods=['GET','POST'])
    async def logs(request:Request,context:AppContext=Depends(get_app_context)):
        service=context.services.production
        return await dispatch(request,context,service.confirm if request.method=='POST' else service.logs,
                              browser=browser,after=request.query_params.get('after'))

    @api.get('/logs/{log_id}')
    async def log(log_id:str,request:Request,context:AppContext=Depends(get_app_context)):
        return await dispatch(request,context,context.services.production.log,log_id,browser=browser)

    @api.post('/logs/{log_id}/reverse')
    async def reverse(log_id:str,request:Request,context:AppContext=Depends(get_app_context)):
        return await dispatch(request,context,context.services.production.reverse,log_id,browser=browser)


add_routes(router,False)
add_routes(browser_router,True)
