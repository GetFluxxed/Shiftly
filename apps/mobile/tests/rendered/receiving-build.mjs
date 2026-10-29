import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const require=createRequire(import.meta.url); const {build}=createRequire(require.resolve('tsx'))('esbuild');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
await build({entryPoints:[path.join(root,'tests/rendered/receiving-entry.tsx')],bundle:true,outfile:process.argv[2],conditions:['expo-source'],platform:'browser',resolveExtensions:['.web.tsx','.web.ts','.web.js','.tsx','.ts','.jsx','.js','.json'],format:'iife',jsx:'automatic',define:{'process.env.NODE_ENV':'"test"',__DEV__:'true'},alias:{'react-native':'react-native-web'},loader:{'.ttf':'dataurl'},plugins:[{name:'receiving-fixtures',setup(b){
  b.onResolve({filter:/SessionProvider$/},()=>({path:'session',namespace:'fixture'}));
  b.onResolve({filter:/WorkspaceProvider$/},()=>({path:'workspace',namespace:'fixture'}));
  b.onResolve({filter:/^expo-router$/},()=>({path:path.join(root,'tests/rendered/router.tsx')}));
  b.onResolve({filter:/^expo-camera$/},()=>({path:path.join(root,'tests/rendered/receiving-camera.tsx')}));
  b.onResolve({filter:/^@expo\/vector-icons\/Ionicons$/},()=>({path:path.join(root,'tests/rendered/icons.tsx')}));
  b.onLoad({filter:/.*/,namespace:'fixture'},({path:name})=>({loader:'tsx',resolveDir:root,contents:name==='session'?`
    const actor={userId:1,businessId:1,storeId:7,username:'owner',displayName:'Owner',role:'owner',provenance:'named',capabilities:['inventory.view','receipts.draft','receipts.post','catalog.manage']};
    const request=(...args)=>window.__receivingRequest(...args);
    export function useSession(){return {status:'ready',actor,stores:[{...actor,storeName:'Fixture Store'}],request};}
  `:`
    import React from 'react'; export function useWorkspace(){return {ready:true,scope:null,message:null};}
    export function useWorkspaceCheckpoint(){return React.useCallback(async()=>true,[]);}
    export function useRememberedState(key,initial,_baseline,validate){const make=()=>typeof initial==='function'?initial():initial;const storageKey='remembered:'+key;const [value,setInner]=React.useState(()=>{try{const raw=sessionStorage.getItem(storageKey);if(raw){const parsed=JSON.parse(raw);if(!validate||validate(parsed))return parsed;}}catch{}return make();});const setValue=action=>setInner(previous=>{const next=typeof action==='function'?action(previous):action;sessionStorage.setItem(storageKey,JSON.stringify(next));return next;});const reset=()=>{sessionStorage.removeItem(storageKey);setInner(make());};return [value,setValue,reset];}
  `}));
}}]});
