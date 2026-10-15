// Exercise the actual browser encoder without microphone or network access.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../../backend/app/ui/access/app.js'), 'utf8');
const start = source.indexOf('  function annotationWav(');
const end = source.indexOf('  async function annotationCapture(', start);
assert.ok(start > 0 && end > start);
class RecordedFile {
  // File snapshots its input bytes; the encoder deliberately clears its scratch buffer.
  constructor(parts, name, options) { this.bytes = new Uint8Array(parts[0]).slice(); this.name = name; this.type = options.type; }
}
const encode = vm.runInNewContext(source.slice(start, end) + '\nannotationWav;', { File: RecordedFile });
const input = new Float32Array(48000);
input.fill(0.25);
const file = encode([input], input.length, 48000);
const view = new DataView(file.bytes.buffer);
assert.equal(file.type, 'audio/wav');
assert.equal(file.bytes.length, 44 + 16000 * 2);
assert.equal(view.getUint32(24, true), 16000);
assert.equal(view.getUint16(22, true), 1);
assert.equal(view.getUint16(34, true), 16);
assert.equal(view.getInt16(44, true), 8191);
console.log('Browser WAV encoder: 16 kHz mono PCM verified.');

const adapterStart = source.indexOf('  async function memoryCommunityCapture(');
const adapterEnd = source.indexOf('  function clearMyUploads(', adapterStart);
assert.ok(adapterStart > 0 && adapterEnd > adapterStart);
function captureAdapter(annotationState, assistantState, annotationCapture) {
  return vm.runInNewContext(source.slice(adapterStart, adapterEnd) + '\nmemoryCommunityCapture;', {
    annotationState, assistantState, annotationCapture, DOMException, AbortController,
  });
}
function fakeCapture(annotationState, { stopped = false } = {}) {
  const handle = {
    stopped,
    stoppedWith: [],
    async stop(keep) {
      if (handle.stopped) return null;
      handle.stopped = true;
      handle.stoppedWith.push(keep);
      if (annotationState.capture === handle) annotationState.capture = null;
      return null;
    },
  };
  return handle;
}
const idleAssistant = () => ({captureAttempt:null,captureStarting:false,capture:null,transcribing:false,
  transcriptionController:null,transcriptReviewPending:false});

(async()=>{
{
  const annotationState = {capture:{storyReservation:true}}, assistantState = idleAssistant();
  let rawCalls = 0;
  const capture = captureAdapter(annotationState, assistantState, async () => { rawCalls++; });
  await assert.rejects(capture(()=>{}), /Microphone already in use/);
  assert.equal(rawCalls, 0);
  assert.deepEqual(annotationState.capture, {storyReservation:true});
}

{
  const annotationState = {capture:null}, assistantState = idleAssistant();
  assistantState.captureAttempt = {starting:true};
  let rawCalls = 0;
  const capture = captureAdapter(annotationState, assistantState, async () => { rawCalls++; });
  await assert.rejects(capture(()=>{}), /Microphone already in use/);
  assert.equal(rawCalls, 0);
  assert.equal(annotationState.capture, null);
}

{
  const annotationState = {capture:null}, assistantState = idleAssistant();
  let optionsSeen;
  const handle = fakeCapture(annotationState);
  const capture = captureAdapter(annotationState, assistantState, async (_ready,_seconds,options) => {
    optionsSeen = options;
    options.signal.addEventListener('abort', () => { void handle.stop(false); }, {once:true});
    return handle;
  });
  const caller = new AbortController();
  const started = await capture(()=>{},30,{signal:caller.signal,isCurrent:()=>true});
  assert.equal(started, handle);
  assert.equal(annotationState.capture, handle);
  assert.equal(typeof optionsSeen.isCurrent, 'function');
  const replacement = {storyReservation:true};
  annotationState.capture = replacement;
  await started.stop(true);
  assert.equal(handle.stoppedWith[0], true);
  assert.equal(annotationState.capture, replacement, 'old handle cleanup must not clear a replacement owner');
}

{
  const annotationState = {capture:null}, assistantState = idleAssistant();
  let resolveRaw, optionsSeen;
  const handle = fakeCapture(annotationState);
  const capture = captureAdapter(annotationState, assistantState, (_ready,_seconds,options) => {
    optionsSeen = options;
    return new Promise(resolve => { resolveRaw = resolve; });
  });
  const starting = capture(()=>{});
  const reservation = annotationState.capture;
  assert.equal(typeof reservation.stop, 'function', 'clearMyUploads can cancel a pending permission/startup request');
  const stopping = reservation.stop(false);
  assert.equal(optionsSeen.signal.aborted, true);
  const replacement = {assistantReservation:true};
  annotationState.capture = replacement;
  resolveRaw(handle);
  await stopping;
  await assert.rejects(starting, error => error?.name === 'AbortError');
  assert.deepEqual(handle.stoppedWith, [false], 'late startup handle is stopped without keeping audio');
  assert.equal(annotationState.capture, replacement, 'late startup cleanup must retain a newer owner');
}

{
  const annotationState = {capture:null}, assistantState = idleAssistant();
  const handle = fakeCapture(annotationState, {stopped:true});
  const capture = captureAdapter(annotationState, assistantState, async () => handle);
  await assert.rejects(capture(()=>{}), /already stopped/);
  assert.equal(annotationState.capture, null, 'an auto-stopped handle must not leave a capture reservation behind');
}

console.log('Shared microphone reservation: contention, startup cancellation, identity release and auto-stop verified.');
})().catch(error=>{console.error(error);process.exitCode=1;});
