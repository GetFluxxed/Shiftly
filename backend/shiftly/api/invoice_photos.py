"""Private native invoice-photo endpoints."""
import psycopg
from fastapi import APIRouter,Depends,Request
from fastapi.responses import JSONResponse
from backend.shiftly.core.dependencies import AppContext,get_app_context
from backend.shiftly.core.http import call,same_origin
from backend.shiftly.core.native import native_token,error_response,unavailable
from backend.shiftly.core.request import RequestBodyError,bounded_json
from backend.shiftly.identity.contracts import IdentityError

router = APIRouter(prefix='/api/mobile/inventory/invoices')


async def dispatch_photo(request, context, operation, *args, max_body=12_000):
    try:
        token = native_token(request)
        if request.method == 'POST':
            same_origin(request)
            fields = await bounded_json(
                request, max_body=max_body,
                invalid_message='Invalid invoice photo request.',
            )
            return await call(operation, token, *args, fields)
        return await call(operation, token, *args)
    except IdentityError as error:
        return error_response(error)
    except (RequestBodyError, ValueError, TypeError, UnicodeError):
        return JSONResponse(
            status_code=400,
            content={
                'error': 'Invalid invoice photo request.',
                'errorCode': 'validation_failed',
            },
        )
    except (psycopg.Error, RuntimeError):
        return unavailable()


@router.post('/{invoice_id}/photo')
async def upload(
    invoice_id: str, request: Request, context: AppContext = Depends(get_app_context),
):
    return await dispatch_photo(
        request, context, context.services.invoice_photos.upload,
        invoice_id, max_body=7_100_000,
    )


@router.get('/{invoice_id}/photo-analysis')
async def analysis(
    invoice_id: str, request: Request, context: AppContext = Depends(get_app_context),
):
    return await dispatch_photo(
        request, context, context.services.invoice_photos.analysis, invoice_id,
    )


@router.post('/{invoice_id}/photo-analysis/retry')
async def retry(
    invoice_id: str, request: Request, context: AppContext = Depends(get_app_context),
):
    return await dispatch_photo(
        request, context, context.services.invoice_photos.retry, invoice_id,
    )
