"""Native store forecast adapter."""
import psycopg
from fastapi import APIRouter,Depends,Request
from fastapi.responses import JSONResponse

from backend.shiftly.core.dependencies import AppContext,get_app_context
from backend.shiftly.core.http import call,same_origin
from backend.shiftly.core.native import native_token,error_response,unavailable
from backend.shiftly.core.request import RequestBodyError,bounded_json
from backend.shiftly.identity.contracts import IdentityError

router=APIRouter(prefix='/api/mobile/production')

@router.api_route('/forecast',methods=['GET','POST'])
async def forecast(request:Request,context:AppContext=Depends(get_app_context)):
    try:
        token=native_token(request); service=context.services.forecasts
        if request.method=='GET':
            return await call(service.get,token,log_id=request.query_params.get('logId'))
        same_origin(request)
        fields=await bounded_json(request,max_body=12000,invalid_message='Invalid forecast request.')
        return await call(service.generate,token,fields)
    except IdentityError as error:return error_response(error)
    except (RequestBodyError,ValueError,TypeError,UnicodeError):
        return JSONResponse(status_code=400,content={'error':'Invalid forecast request.','errorCode':'validation_failed'})
    except (psycopg.Error,RuntimeError):return unavailable()
