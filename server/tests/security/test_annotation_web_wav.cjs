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
