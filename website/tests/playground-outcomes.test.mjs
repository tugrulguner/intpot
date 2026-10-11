import test from 'node:test';
import assert from 'node:assert/strict';
import { createOutcomeTracker } from '../src/lib/playground-outcomes.mjs';
test('listener receives paired unique outcome events with no editable request data', () => {
 const events=[]; let id=0; const tracker=createOutcomeTracker('intpot',(event,properties)=>events.push({event,properties}),()=>`attempt-${++id}`);
 const one=tracker.start('HTTP'); assert.equal(tracker.complete(one,'rejected','validation'),true);
 const two=tracker.start('MCP'); tracker.complete(two,'success');
 assert.deepEqual(events.map(e=>e.event),['playground_preview_started','playground_preview_completed','playground_preview_started','playground_preview_completed']);
 assert.deepEqual(events.map(e=>e.properties.attempt_id),['attempt-1','attempt-1','attempt-2','attempt-2']);
 assert.deepEqual(events[1].properties,{project:'intpot',mode:'HTTP',attempt_id:'attempt-1',result:'rejected',failure_class:'validation'});
 assert.deepEqual(events[3].properties,{project:'intpot',mode:'MCP',attempt_id:'attempt-2',result:'success'});
 assert.equal(tracker.complete(one,'success'),false);
});
test('tracker rejects unbounded fields and malformed failure/result pairs',()=>{const tracker=createOutcomeTracker('intpot',()=>{});assert.throws(()=>tracker.start('free text'),/mode/);const attempt=tracker.start('CLI');assert.throws(()=>tracker.complete(attempt,'success','execution'),/failure class/);assert.throws(()=>tracker.complete(attempt,'failure'),/result/);});
