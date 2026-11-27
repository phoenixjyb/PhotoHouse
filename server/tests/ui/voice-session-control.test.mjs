import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
const root = {};
vm.runInNewContext(fs.readFileSync(new URL('../../backend/app/ui/access/voice-session-control.js', import.meta.url), 'utf8'), root);
const classify = root.PhotoHouseVoiceSessionControl;
test('recognizes only the complete Chinese and English controls', () => {
  for (const value of ['暂停', '暂停聆听', '暂停语音', 'pause', 'pause listening', 'pause voice chat', 'pause voice search', 'stop']) assert.equal(classify(value), 'pause', value);
  for (const value of ['结束', '结束语音', '结束对话', '停止聆听', 'end voice chat', 'end voice search', 'stop listening']) assert.equal(classify(value), 'end', value);
});
test('accepts terminal ASR punctuation case and surrounding whitespace', () => {
  for (const [value, expected] of [[' 暂停。 ', 'pause'], ['PAUSE!?', 'pause'], ['\nStop listening！\t', 'end'], [' 结束语音。！？', 'end']]) assert.equal(classify(value), expected, value);
});
test('negated quoted compound or near-match requests are never controls', () => {
  for (const value of ['不要暂停', '不要结束语音', '找暂停时拍的照片', 'pause the video', 'please pause', '暂停，然后找照片', '结束语音后找照片', '“暂停”', '"pause"', 'stop listening to music', 'unpause', 'pause,', 'pause\nlistening', 'pause\u200blistening', 'pause…', '暂停吧', 'end', 'resume', '继续', '.pause', '。暂停', 'pa.use', 'pause .', '暂停 。']) assert.equal(classify(value), null, value);
});
test('rejects absent oversized or malformed transcript values', () => {
  for (const value of [null, undefined, 1, {}, '', '   ', ' '.repeat(1024) + 'pause', '\ud800pause', 'pause\udfff']) assert.equal(classify(value), null);
});

test('recognizes only complete Web reading-continuation commands', () => {
  for (const value of ['继续朗读', '继续读', '读下一段', 'continue reading', 'read the next part', 'read the next segment', ' CONTINUE READING。 ']) assert.equal(classify(value), 'continue_reading', value);
  for (const value of ['继续', '不要继续朗读', '继续朗读另一章', 'continue reading about Jane', 'please continue reading', '“继续朗读”', 'read the next part of another story']) assert.equal(classify(value), null, value);
});

test('paged results recognize complete bilingual numbered commands', () => {
  const number = root.PhotoHouseVoiceResultNumber;
  for (const [input, expected] of [
    ['打开第21项', 21], ['打开第二十一项。', 21], [' 打开第２３个结果 ', 23],
    ['打开第一百零二项', 102], ['打开第一千零一十项', 1010], ['Open item 21.', 21],
    ['open item twenty-one', 21], ['open result number eighty six', 86],
    ['open the 21st result', 21], ['open the 112th result', 112],
  ]) assert.equal(number(input), expected, input);
  for (const input of [
    '打开第一百二项', '打开第一百零二十项', '打开第零项', '不要打开第21项',
    '打开第21项，然后找视频', '打开编号21', '“打开第21项”', 'open item 0',
    'open item 021', 'open item 21 or 22', 'do not open item 21', 'open the 21th result',
    'open item twenty thirteen', 'open item\n21', null,
  ]) assert.equal(number(input), null, input);
});
