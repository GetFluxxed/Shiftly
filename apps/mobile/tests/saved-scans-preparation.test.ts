/// <reference types="node" />
import assert from 'node:assert/strict';
import test from 'node:test';
import type { Snapshot } from '../src/session/controller';
import { SavedScansController } from '../src/inventory/scans/controller';
import { prepareSavedScans } from '../src/inventory/scans/prepare';
const owner = { userId: 1, businessId: 2, storeId: 3 };
function harness(read: () => Promise<string | null>) {
  let snapshot: Snapshot = { status: 'ready', actor: { ...owner, username:'Owner',displayName:'Owner',provenance:'named',role:'owner',capabilities:['inventory.view','catalog.manage'] }, stores:[], busy:false, message:null,revision:1 };
  let granted = 0;
  const session = {getSnapshot:()=>snapshot,canCaptureScans:()=>['ready','offline'].includes(snapshot.status),
    authorizeOfflineCatalogCapture:async()=>{granted++;}};
  const controller=new SavedScansController(()=>({read,write:async()=>undefined,remove:async()=>undefined}),()=>session.canCaptureScans());
  return {session,controller,granted:()=>granted,change:(change:Partial<Snapshot>)=>{snapshot={...snapshot,...change};}};
}
test('preparation waits for a readable durable inbox before granting offline capture',async()=>{
  let finish!:(value:null)=>void;const gate=new Promise<null>(resolve=>{finish=resolve;});
  const h=harness(()=>gate);
  const preparing=prepareSavedScans(h.session,h.controller);
  await Promise.resolve();assert.equal(h.controller.getSnapshot().status,'loading');assert.equal(h.granted(),0);
  finish(null);await preparing;assert.equal(h.controller.getSnapshot().status,'ready');assert.equal(h.granted(),1);
});
test('failed or corrupt inbox hydration never grants offline capture',async()=>{
 for(const read of [async()=>{throw new Error('disk unavailable');},async()=>'{corrupt']){
   const h=harness(read);await assert.rejects(prepareSavedScans(h.session,h.controller),/could not be restored/);
   assert.equal(h.granted(),0);assert.equal(h.controller.getSnapshot().status,'error');
 }
});
test('scope/session change during hydration cannot prepare offline access',async()=>{
 let finish!:(value:null)=>void;const gate=new Promise<null>(resolve=>{finish=resolve;});
 const h=harness(()=>gate);const preparing=prepareSavedScans(h.session,h.controller);
 h.change({status:'locked',revision:2,actor:null});finish(null);
 await assert.rejects(preparing,/account or store changed/);assert.equal(h.granted(),0);
});
test('recovery under an existing offline lease never renews the permission',async()=>{
 const h=harness(async()=>null);h.change({status:'offline'});await prepareSavedScans(h.session,h.controller);
 assert.equal(h.controller.getSnapshot().status,'ready');assert.equal(h.granted(),0);
});
