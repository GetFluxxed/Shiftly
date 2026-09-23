"""Native catalog/storage endpoints, independent of accounts/report routers."""
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
            fields = await bounded_json(request, max_body=12_000, invalid_message='Invalid inventory request.')
            return await call(operation, token, *args, fields)
        return await call(operation, token, *args, **kwargs)
    except IdentityError as error:
        return error_response(error)
    except (RequestBodyError, ValueError, TypeError, UnicodeError):
        return JSONResponse(status_code=400, content={'error': 'Invalid inventory request.', 'errorCode': 'validation_failed'})
    except (psycopg.Error, RuntimeError):
        return unavailable()


@router.api_route('/products', methods=['GET', 'POST'])
async def products(request: Request, context: AppContext = Depends(get_app_context)):
    service = context.services.inventory
    return await dispatch(request, context, service.create_product if request.method == 'POST' else service.products,
                          query=request.query_params.get('q', ''), after=request.query_params.get('after'), state=request.query_params.get('state', 'active'))


@router.api_route('/products/{product_id}', methods=['GET', 'POST'])
async def product(product_id: str, request: Request, context: AppContext = Depends(get_app_context)):
    service = context.services.inventory
    return await dispatch(request, context, service.edit_product if request.method == 'POST' else service.product, product_id)


@router.post('/products/{product_id}/state')
async def product_state(product_id: str, request: Request, context: AppContext = Depends(get_app_context)):
    return await dispatch(request, context, context.services.inventory.product_state, product_id)


@router.api_route('/shelves', methods=['GET', 'POST'])
async def shelves(request: Request, context: AppContext = Depends(get_app_context)):
    service = context.services.inventory
    return await dispatch(request, context, service.create_shelf if request.method == 'POST' else service.shelves,
                          after=request.query_params.get('after'))


@router.api_route('/shelves/{shelf_id}', methods=['GET', 'POST'])
async def shelf(shelf_id: str, request: Request, context: AppContext = Depends(get_app_context)):
    service = context.services.inventory
    return await dispatch(request, context, service.edit_shelf if request.method == 'POST' else service.shelf, shelf_id,
                          after=request.query_params.get('after'))


@router.post('/shelves/{shelf_id}/products/{product_id}')
async def placement(shelf_id: str, product_id: str, request: Request, context: AppContext = Depends(get_app_context)):
    return await dispatch(request, context, context.services.inventory.place, shelf_id, product_id)
