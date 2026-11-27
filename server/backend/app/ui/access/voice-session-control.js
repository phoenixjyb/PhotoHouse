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
  const smallEnglish = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight',
    'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen'];
  const tensEnglish = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'];
  const chineseDigits = '零一二三四五六七八九';
  function readItemNumber(value) {
    if (/^[1-9][0-9]{0,7}$/u.test(value)) return Number(value);
    const english = /^(?:([a-z]+)[ -])?([a-z]+)$/u.exec(value);
    if (english) {
      const units = smallEnglish.indexOf(english[2]), tens = tensEnglish.indexOf(english[1] || english[2]);
      if (english[1]) return tens >= 2 && units >= 1 && units <= 9 ? tens * 10 + units : null;
      return units > 0 ? units : tens >= 2 ? tens * 10 : null;
    }
    // Each place may occur once, in descending order. A zero only bridges
    // omitted places, and only bare 十 may imply a leading one.
    const chinese = /^(?=.+$)(?:([一二三四五六七八九])千)?(?:(?:零)?([一二三四五六七八九])百)?(?:(?:零)?([一二三四五六七八九]?)十)?(?:(?:零)?([一二三四五六七八九]))?$/u.exec(value);
    if (!chinese || value.startsWith('零') || (chinese[3] === '' && !value.startsWith('十'))) return null;
    const digit = character => character ? chineseDigits.indexOf(character) : 0;
    const number = digit(chinese[1]) * 1000 + digit(chinese[2]) * 100 +
      (chinese[3] === '' ? 10 : digit(chinese[3]) * 10) + digit(chinese[4]);
    // Refuse shorthand like 一百二, which could mean 102 or 120.
    let canonical = '', gap = false;
    for (const [place, unit] of [[1000, '千'], [100, '百'], [10, '十'], [1, '']]) {
      const current = Math.floor(number / place) % 10;
      if (!current) { gap ||= !!canonical; continue; }
      if (gap) canonical += '零';
      if (place !== 10 || current !== 1 || canonical) canonical += chineseDigits[current];
      canonical += unit;
      gap = false;
    }
    return number > 0 && canonical === value ? number : null;
  }
  root.PhotoHouseVoiceResultNumber = text => {
    if (typeof text !== 'string' || text.length > 128) return null;
    const value = text.trim().replace(/[０-９]/gu, c => String(c.charCodeAt(0) - 0xFF10))
      .toLowerCase().replace(/[.!?。！？]+$/u, '');
    const chinese = /^打开第[ ]*([一二三四五六七八九十百千零0-9]+)[ ]*(?:项|个结果)$/u.exec(value);
    if (chinese) return readItemNumber(chinese[1]);
    const english = /^open (?:result|item)(?: number)? ([a-z0-9 -]+)$/u.exec(value);
    if (english) return readItemNumber(english[1]);
    const ordinal = /^open the ([1-9][0-9]{0,7})(st|nd|rd|th) (?:result|item)$/u.exec(value);
    if (!ordinal) return null;
    const number = Number(ordinal[1]);
    const suffix = number % 100 >= 11 && number % 100 <= 13 ? 'th' : ({1:'st',2:'nd',3:'rd'}[number % 10] || 'th');
    return ordinal[2] === suffix ? number : null;
  };
})(typeof window === 'undefined' ? globalThis : window);
