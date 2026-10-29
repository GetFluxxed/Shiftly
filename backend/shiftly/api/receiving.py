"""Native invoice-draft and incoming-preview endpoints."""
import psycopg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from backend.shiftly.core.dependencies import AppContext, get_app_context
from backend.shiftly.core.http import call, same_origin
from backend.shiftly.core.native import native_token, error_response, unavailable
from backend.shiftly.core.request import RequestBodyError, bounded_json
from backend.shiftly.identity.contracts import IdentityError

router = APIRouter(prefix='/api/mobile/inventory')


async def dispatch(request, context, operation, *args, **kwargs):
    try:
        token = native_token(request)
        if request.method == 'POST':
            same_origin(request)
            fields = await bounded_json(request, max_body=80_000, invalid_message='Invalid invoice request.')
            return await call(operation, token, *args, fields)
        return await call(operation, token, *args, **kwargs)
    except IdentityError as error:
        return error_response(error)
    except (RequestBodyError, ValueError, TypeError, UnicodeError):
        return JSONResponse(status_code=400, content={'error': 'Invalid invoice request.', 'errorCode': 'validation_failed'})
    except (psycopg.Error, RuntimeError):
        return unavailable()


@router.api_route('/invoices', methods=['GET', 'POST'])
async def invoices(request: Request, context: AppContext = Depends(get_app_context)):
    service = context.services.receiving
    return await dispatch(request, context, service.create if request.method == 'POST' else service.invoices,
                          query=request.query_params.get('q', ''), after=request.query_params.get('after'))


@router.api_route('/invoices/{invoice_id}', methods=['GET', 'POST'])
async def invoice(invoice_id: str, request: Request, context: AppContext = Depends(get_app_context)):
    service = context.services.receiving
    return await dispatch(request, context, service.edit if request.method == 'POST' else service.invoice, invoice_id)


@router.post('/invoices/{invoice_id}/close')
async def close(invoice_id: str, request: Request, context: AppContext = Depends(get_app_context)):
    return await dispatch(request, context, context.services.receiving.close, invoice_id)


@router.post('/invoices/{invoice_id}/rebase')
async def rebase(invoice_id: str, request: Request, context: AppContext = Depends(get_app_context)):
    return await dispatch(request, context, context.services.receiving.rebase, invoice_id)


@router.get('/incoming')
async def incoming(request: Request, context: AppContext = Depends(get_app_context)):
    return await dispatch(request, context, context.services.receiving.incoming,
                          query=request.query_params.get('q', ''), after=request.query_params.get('after'))
