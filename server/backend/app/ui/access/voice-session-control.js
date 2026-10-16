/* Exact local controls for an already opted-in foreground voice session. */
((root) => {
  'use strict';
  const pause = new Set(['暂停', '暂停聆听', '暂停语音', 'pause', 'pause listening', 'pause voice chat', 'pause voice search', 'stop']);
  const reading = new Set(['继续朗读', '继续读', '读下一段', 'continue reading', 'read the next part', 'read the next segment']);
  const end = new Set(['结束', '结束语音', '结束对话', '停止聆听', 'end voice chat', 'end voice search', 'stop listening']);
  // This is intentionally not a natural-language intent parser. Quotes, negation,
  // internal punctuation and additional words must remain ordinary requests.
  root.PhotoHouseVoiceSessionControl = text => {
    if (typeof text !== 'string' || text.length > 1024 || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(text)) return null;
    const value = text.trim().replace(/[A-Z]/g, c => c.toLowerCase()).replace(/[.!?。！？]+$/u, '');
    return pause.has(value) ? 'pause' : end.has(value) ? 'end' : reading.has(value) ? 'continue_reading' : null;
  };
})(typeof window === 'undefined' ? globalThis : window);
