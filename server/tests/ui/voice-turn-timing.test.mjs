import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const root = {};
vm.runInNewContext(fs.readFileSync(new URL('../../backend/app/ui/access/voice-turn-timing.js', import.meta.url), 'utf8'), root);
const factory = root.PhotoHouseVoiceTurnTiming;
const state = (phase, changes={}) => ({scopeKey:'synthetic-scope',appGeneration:1,sessionGeneration:1,operationGeneration:1,
  phase,captureStarted:false,playbackStarted:false,...changes});
const plain = value => value && JSON.parse(JSON.stringify(value));
function journey(tracker, clock) {
  tracker.observe(state('listening'));clock.value=10;
  tracker.observe(state('listening',{captureStarted:true}));clock.value=100;
  tracker.observe(state('transcribing',{operationGeneration:2}));clock.value=350;
  tracker.observe(state('requesting',{operationGeneration:3}));clock.value=750;
  tracker.observe(state('speaking',{operationGeneration:4}));clock.value=1000;
  tracker.observe(state('speaking',{operationGeneration:4,playbackStarted:true}));clock.value=3000;
  return tracker.observe(state('listening',{operationGeneration:5}));
}

test('only a complete successful turn returns client-observed durations without identities', () => {
  const clock={value:0},tracker=factory(()=>clock.value);
  assert.deepEqual(plain(journey(tracker,clock)),{transcriptionMillis:250,requestMillis:400,speechPreparationMillis:250,playbackMillis:2000});
  const snapshot=tracker.summary();snapshot.requestMillis=999;
  assert.equal(tracker.summary().requestMillis,400);
  assert.equal(JSON.stringify(tracker.summary()).includes('synthetic'),false);
});
test('pause, end, idle and session changes clear timings', () => {
  for (const phase of ['paused','ended','idle']) {
    const clock={value:0},tracker=factory(()=>clock.value);journey(tracker,clock);
    assert.equal(tracker.observe(state(phase,{operationGeneration:6})),null);
    assert.equal(tracker.summary(),null);
  }
  const clock={value:0},tracker=factory(()=>clock.value);journey(tracker,clock);
  assert.equal(tracker.observe(state('listening',{sessionGeneration:2,operationGeneration:1})),null);
});
test('older observations cannot replace a current completed summary', () => {
  const clock={value:0},tracker=factory(()=>clock.value);journey(tracker,clock);
  const before=plain(tracker.summary());
  assert.deepEqual(plain(tracker.observe(state('paused',{operationGeneration:4}))),before);
  assert.deepEqual(plain(tracker.observe(state('ended',{sessionGeneration:0}))),before);
});
test('an older account scope cannot revive a turn after a newer scope completes', () => {
  let now=0;const tracker=factory(()=>now++);
  const cycle=(scopeKey,appGeneration)=>[
    state('listening',{scopeKey,appGeneration,captureStarted:true}),
    state('transcribing',{scopeKey,appGeneration,operationGeneration:2}),
    state('requesting',{scopeKey,appGeneration,operationGeneration:3}),
    state('speaking',{scopeKey,appGeneration,operationGeneration:4}),
    state('speaking',{scopeKey,appGeneration,operationGeneration:4,playbackStarted:true}),
    state('listening',{scopeKey,appGeneration,operationGeneration:5}),
  ];
  for(const observation of cycle('new-scope',2)) tracker.observe(observation);
  const current=plain(tracker.summary());assert.ok(current);
  for(const observation of cycle('old-scope',1)) assert.deepEqual(plain(tracker.observe(observation)),current);
  assert.equal(tracker.observe(state('listening',{scopeKey:'replacement-without-generation',appGeneration:2,operationGeneration:6})),null);
  assert.equal(tracker.summary(),null);
});
test('phase skips, unconfirmed capture or playback and failures produce no summary', () => {
  for (const sequence of [
    [state('listening'),state('transcribing'),state('requesting'),state('speaking'),state('speaking',{playbackStarted:true}),state('listening')],
    [state('listening',{captureStarted:true}),state('requesting'),state('speaking'),state('listening')],
    [state('listening',{captureStarted:true}),state('transcribing'),state('requesting'),state('speaking'),state('listening')],
    [state('listening',{captureStarted:true}),state('transcribing'),state('paused'),state('requesting'),state('speaking',{playbackStarted:true}),state('listening')],
  ]) {
    let now=0;const tracker=factory(()=>now++);
    for(const observation of sequence)tracker.observe(observation);
    assert.equal(tracker.summary(),null);
  }
});
test('bad clocks, malformed observations and source scopes cannot retain timings', () => {
  for(const bad of [-1,NaN,Infinity,Number.MAX_SAFE_INTEGER+1]) {
    const clock={value:0},tracker=factory(()=>clock.value);journey(tracker,clock);clock.value=bad;
    assert.equal(tracker.observe(state('listening',{operationGeneration:6,captureStarted:true})),null);
  }
  const clock={value:0},tracker=factory(()=>clock.value);journey(tracker,clock);clock.value=2000;
  assert.equal(tracker.observe(state('listening',{operationGeneration:6,captureStarted:true})),null);
  clock.value=4000;journey(tracker,{value:0});
  assert.equal(tracker.observe({...state('listening'),scopeKey:'another-synthetic-scope'}),null);
  assert.equal(tracker.observe({...state('listening'),phase:'unknown'}),null);
});

test('a clock fault fences the session until a new explicit generation', () => {
  const clock={value:0},tracker=factory(()=>clock.value);journey(tracker,clock);clock.value=1;
  tracker.observe(state('listening',{operationGeneration:6,captureStarted:true}));
  clock.value=10000;assert.equal(tracker.observe(state('transcribing',{operationGeneration:7})),null);
  assert.equal(tracker.observe(state('listening',{sessionGeneration:2,operationGeneration:1})),null);
  clock.value=10100;tracker.observe(state('listening',{sessionGeneration:2,operationGeneration:1,captureStarted:true}));
  clock.value=10200;tracker.observe(state('transcribing',{sessionGeneration:2,operationGeneration:2}));
  clock.value=10300;tracker.observe(state('requesting',{sessionGeneration:2,operationGeneration:3}));
  clock.value=10400;tracker.observe(state('speaking',{sessionGeneration:2,operationGeneration:4}));
  clock.value=10500;tracker.observe(state('speaking',{sessionGeneration:2,operationGeneration:4,playbackStarted:true}));
  clock.value=10600;assert(tracker.observe(state('listening',{sessionGeneration:2,operationGeneration:5})));
});
