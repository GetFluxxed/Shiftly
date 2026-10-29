"""Native stock/count endpoints; lifecycle rules stay in the count service."""
from fastapi import APIRouter, Depends, Request
from backend.shiftly.core.dependencies import AppContext, get_app_context
from .inventory import dispatch

router = APIRouter(prefix='/api/mobile/inventory')


@router.get('/count-status')
async def status(request: Request, context: AppContext = Depends(get_app_context)):
    return await dispatch(request,context,context.services.counts.dashboard)


@router.get('/stock')
async def stock(request: Request, context: AppContext = Depends(get_app_context)):
    return await dispatch(request,context,context.services.counts.stock,
                          query=request.query_params.get('q',''),after=request.query_params.get('after'),shelf=request.query_params.get('shelf',''))


@router.get('/stock/{product_id}')
async def stock_detail(product_id: str, request: Request, context: AppContext = Depends(get_app_context)):
    return await dispatch(request,context,context.services.counts.stock_detail,product_id,after=request.query_params.get('after'))


@router.api_route('/counts',methods=['GET','POST'])
async def counts(request: Request, context: AppContext = Depends(get_app_context)):
    return await dispatch(request,context,context.services.counts.start if request.method=='POST' else context.services.counts.history,
                          after=request.query_params.get('after'))


@router.get('/counts/{count_id}')
async def count_detail(count_id: str, request: Request, context: AppContext = Depends(get_app_context)):
    return await dispatch(request,context,context.services.counts.detail,count_id)


@router.get('/counts/{count_id}/lines')
async def lines(count_id: str, request: Request, context: AppContext = Depends(get_app_context)):
    missing = request.query_params.get('missing','false')
    return await dispatch(request,context,context.services.counts.lines,count_id,query=request.query_params.get('q',''),
                          after=request.query_params.get('after'),shelf=request.query_params.get('shelf',''),
                          missing={'true':True,'false':False}.get(missing,missing))


@router.get('/counts/{count_id}/lines/{line_id}')
async def line(count_id: str, line_id: str, request: Request, context: AppContext = Depends(get_app_context)):
    return await dispatch(request,context,context.services.counts.line,count_id,line_id)


@router.post('/counts/{count_id}/lines/{line_id}')
async def save(count_id: str, line_id: str, request: Request, context: AppContext = Depends(get_app_context)):
    return await dispatch(request,context,context.services.counts.save,count_id,line_id)


@router.get('/counts/{count_id}/comparison')
async def comparison(count_id: str, request: Request, context: AppContext = Depends(get_app_context)):
    return await dispatch(request,context,context.services.counts.comparisons,count_id,query=request.query_params.get('q',''),after=request.query_params.get('after'))


@router.post('/counts/{count_id}/{action}')
async def transition(count_id: str, action: str, request: Request, context: AppContext = Depends(get_app_context)):
    return await dispatch(request,context,context.services.counts.transition,count_id,action)
