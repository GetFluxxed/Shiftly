import React from 'react';
import { createRoot } from 'react-dom/client';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Alert, AppState } from 'react-native';
import { RouterContext } from './router';
import { IncomingScreen, InvoiceListScreen, InvoiceScreen } from '../../src/inventory/receiving/ReceivingScreens';
import { InvoicePhotoScreen } from '../../src/inventory/receiving/InvoiceCamera';

const invoiceId = '11111111-1111-4111-8111-111111111111';
const secondInvoiceId = '44444444-4444-4444-8444-444444444444';
const productId = '22222222-2222-4222-8222-222222222222';
const scenario = new URL(location.href).searchParams.get('scenario');
const fixtureVersion = Number(new URL(location.href).searchParams.get('version') || '1');
const packageId = '55555555-5555-4555-8555-555555555555';
const baseInvoice = (id=invoiceId): any => ({ id, storeId: 7, supplier: '', invoiceNumber: '', state: 'draft', version: 1, lineCount: 0, receivedCount: 0, updatedAt: '2026-10-25T10:00:00Z', createdAt: '2026-10-25T10:00:00Z', baselineCountId: null, needsCountReview: false, needsCatalogReview: false, photoReadingAvailable: true, lines: [] });
let invoice: any = baseInvoice();
if (scenario === 'concurrency') invoice = { ...invoice, version: fixtureVersion };
if (scenario === 'rebase') invoice = { ...invoice, needsCountReview: true };
if (scenario === 'photo-unavailable') invoice = { ...invoice, photoReadingAvailable: false };
if (scenario === 'closed' || scenario === 'package') invoice = { ...invoice, state: scenario === 'closed' ? 'closed' : 'draft', lineCount: 1, lines: [{ id: '66666666-6666-4666-8666-666666666666', description: 'Milk case', sku: 'MILK-01', productId, packageId, quantity: '2', unit: 'package', received: false, productName: 'Milk', baseUnit: 'kg', normalizedQuantity: '20', packageName: '10 kg case', needsCatalogReview: false }] };
let analysis: any = scenario === 'retry' ? { id: '33333333-3333-4333-8333-333333333333', state: 'failed', canRetry: true, message: 'Try again.', supplier: null, invoiceNumber: null, lines: [] } : { id: null, state: 'none', canRetry: false, message: null, supplier: null, invoiceNumber: null, lines: [] };
let creates=0; (window as any).__createRequestIds=[];
const subscribe = AppState.addEventListener.bind(AppState);
AppState.addEventListener = ((event: string, listener: (...args: any[]) => void) => event === 'change' ? subscribe(event as 'change', listener) : { remove() {} }) as typeof AppState.addEventListener;
Alert.alert = ((_title: string, _message?: string, actions?: { style?: string; onPress?: () => void }[]) => { (actions?.find(action => action.style === 'destructive') || actions?.at(-1))?.onPress?.(); }) as typeof Alert.alert;
(window as any).__receivingRequest = async (path: string, options: any = {}) => {
  if (path === '/inventory/invoices' && options.method === 'POST') { (window as any).__createRequestIds.push(options.body.requestId); invoice=baseInvoice(creates++ ? secondInvoiceId : invoiceId); return invoice; }
  if (path === '/inventory/invoices') return { items: creates ? [invoice] : [], nextCursor: null, photoReadingAvailable: true };
  if (path === '/inventory/products') return {items:[{id:productId,name:'Milk',sku:'MILK-01',baseUnit:'kg',active:true,version:1,containerAmount:null,containerLabelAmount:null,containerLabelUnit:null}],nextCursor:null};
  if (path === '/inventory/incoming') { const line=invoice.state==='draft' ? invoice.lines.find((value:any)=>value.productId===productId) : null; const amount=line ? (line.packageId ? String(Number(line.quantity)*10) : line.quantity) : '0'; return {items:line?[{productId,name:'Milk',baseUnit:'kg',currentQuantity:'5',incomingQuantity:amount,receivedQuantity:line.received?amount:'0',projectedQuantity:String(5+Number(amount))}]:[],nextCursor:null,unmatchedCount:0,needsCountReview:false,needsCatalogReview:false}; }
  if (path.endsWith('/photo') && options.method === 'POST') { analysis = { id: '33333333-3333-4333-8333-333333333333', state: 'ready', canRetry: false, message: null, supplier: 'Dairy Co', invoiceNumber: '00042', lines: [{ description: 'Milk', sku: 'MILK-01', quantity: '2.500', unit: 'kg', productId, packageId: null }] }; return analysis; }
  if (path.endsWith('/photo-analysis/retry') && options.method === 'POST') { analysis={...analysis,state:'queued',canRetry:false,message:null}; return analysis; }
  if (path.endsWith('/photo-analysis')) { if (analysis.state==='queued') analysis={id:analysis.id,state:'ready',canRetry:false,message:null,supplier:'Retry Supplier',invoiceNumber:'R-1',lines:[]}; return analysis; }
  if (path === `/inventory/products/${productId}/packages`) return {items:[{id:packageId,productId,name:'10 kg case',amount:'10',labelAmount:null,labelUnit:null,kind:'case',active:true,version:1,isDefault:false,containedPackageId:null,containedCount:null,barcodes:[]}],nextCursor:null};
  if (path === `/inventory/products/${productId}`) return {id:productId,name:'Milk',sku:'MILK-01',baseUnit:'kg',active:true,version:1,containerAmount:null,containerLabelAmount:null,containerLabelUnit:null};
  if (path.endsWith('/rebase') && options.method === 'POST') { invoice={...invoice,version:invoice.version+1,needsCountReview:false}; return invoice; }
  if (path.endsWith('/close') && options.method === 'POST') { invoice={...invoice,state:'closed',version:invoice.version+1}; return invoice; }
  if (/\/inventory\/invoices\/[0-9a-f-]{36}$/.test(path) && options.method === 'POST') { const bodies=JSON.parse(sessionStorage.getItem('saveBodies') || '[]'); bodies.push(options.body); sessionStorage.setItem('saveBodies',JSON.stringify(bodies)); if (scenario === 'concurrency') throw new Error('Unable to confirm save'); invoice = { ...invoice, ...options.body, version: invoice.version + 1, lineCount: options.body.lines.length, receivedCount: options.body.lines.filter((line:any)=>line.received).length, lines: options.body.lines.map((line: any) => ({ ...line, productName: line.productId?'Milk':null, baseUnit: line.productId?'kg':null, normalizedQuantity: line.quantity, packageName: line.packageId?'10 kg case':null, needsCatalogReview: false })) }; return invoice; }
  if (/\/inventory\/invoices\/[0-9a-f-]{36}$/.test(path)) return invoice;
  throw new Error(`Unexpected request ${path}`);
};

function App() {
  const detailScenario = ['closed','package','retry','concurrency','rebase','photo-unavailable'].includes(scenario || '');
  const [route, setRoute] = React.useState(scenario === 'incoming' ? {path:'/incoming',params:{} as Record<string,string>} : detailScenario ? { path: '/invoices/[invoiceId]', params: {invoiceId} as Record<string,string> } : { path: '/invoices', params: {} as Record<string,string> });
  const go = (value: any) => { let path = typeof value === 'string' ? value : value.pathname; const params = { ...(typeof value === 'string' ? {} : value.params || {}) }; const match = path.match(/^\/invoices\/([0-9a-f-]{36})(\/photo)?$/); if (match) { params.invoiceId = match[1]; path = match[2] ? '/invoices/[invoiceId]/photo' : '/invoices/[invoiceId]'; } setRoute({ path, params }); };
  (window as any).__receivingGo=go;
  const Screen = route.path === '/incoming' ? IncomingScreen : route.path === '/invoices/[invoiceId]/photo' ? InvoicePhotoScreen : route.path === '/invoices/[invoiceId]' ? InvoiceScreen : InvoiceListScreen;
  return <SafeAreaProvider><RouterContext.Provider value={{ go, replace: go, dismissTo: go, path: route.path, params: route.params, setParams: () => {} }}><Screen /></RouterContext.Provider></SafeAreaProvider>;
}
createRoot(document.getElementById('root')!).render(<App />);
