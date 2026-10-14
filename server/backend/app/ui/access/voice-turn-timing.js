/* Local client observations only. No words, source IDs, storage or network. */
((root) => {
  'use strict';
  root.PhotoHouseVoiceTurnTiming = (clock = () => Math.floor(root.performance.now())) => {
    if (typeof clock !== 'function') throw new TypeError('Timing clock required');
    const phases = new Set(['idle','listening','transcribing','requesting','speaking','paused','ended']);
    let identity = null, appGeneration = -1, session = -1, operation = -1, stage = null, lastTime = null;
    let blocked = false, closed = false;
    let recognitionStart = null, requestStart = null, preparationStart = null, playbackStart = null;
    let transcriptionMillis = null, requestMillis = null, speechPreparationMillis = null, summary = null;
    const clearRound = () => {
      stage = null; lastTime = null; recognitionStart = requestStart = preparationStart = playbackStart = null;
      transcriptionMillis = requestMillis = speechPreparationMillis = null; summary = null;
    };
    const reset = () => { identity = null; appGeneration = session = operation = -1; blocked = closed = false; clearRound(); };
    const number = value => Number.isSafeInteger(value) && value >= 0;
    const result = () => summary ? {...summary} : null;
    const observe = (state) => {
      if (!state || typeof state !== 'object' || typeof state.scopeKey !== 'string' ||
          !state.scopeKey || state.scopeKey.length > 1024 || !number(state.appGeneration) || !number(state.sessionGeneration) ||
          !number(state.operationGeneration) || !phases.has(state.phase) ||
          typeof state.captureStarted !== 'boolean' || typeof state.playbackStarted !== 'boolean') {
        reset(); return null;
      }
      // Late callbacks cannot replace the current session's timings.
      if (state.appGeneration < appGeneration || state.appGeneration === appGeneration && (state.sessionGeneration < session ||
          state.sessionGeneration === session && state.operationGeneration < operation)) return result();
      // Account/library identity may only change with a new app scope. A
      // same-generation identity replacement must never revive old observations.
      if (identity !== null && state.appGeneration === appGeneration && identity !== state.scopeKey) {
        clearRound(); blocked = true; return null;
      }
      if (state.appGeneration !== appGeneration || session !== state.sessionGeneration) {
        reset(); identity = state.scopeKey; appGeneration = state.appGeneration; session = state.sessionGeneration;
        if (!['idle','paused','ended','listening'].includes(state.phase)) blocked = true;
      }
      operation = state.operationGeneration;
      if (['idle','paused','ended'].includes(state.phase)) { clearRound(); closed = true; return null; }
      if (blocked || closed) return null;
      if (state.captureStarted && state.phase !== 'listening' || state.playbackStarted && state.phase !== 'speaking') {
        clearRound(); blocked = true; return null;
      }
      let now;
      try { now = clock(); } catch { clearRound(); blocked = true; return null; }
      if (!number(now) || lastTime !== null && now < lastTime) { clearRound(); blocked = true; return null; }
      lastTime = now;
      const next = state.phase === 'listening' ? (state.captureStarted ? 'listening' : 'capture_preparing') :
        state.phase === 'speaking' ? (state.playbackStarted ? 'playback' : 'speech_preparing') : state.phase;
      if (next === stage) return result();
      if (next === 'capture_preparing' || next === 'listening') {
        if (stage === 'playback' && playbackStart !== null && transcriptionMillis !== null &&
            requestMillis !== null && speechPreparationMillis !== null) {
          summary = {transcriptionMillis, requestMillis, speechPreparationMillis, playbackMillis: now-playbackStart};
          recognitionStart = requestStart = preparationStart = playbackStart = null;
          transcriptionMillis = requestMillis = speechPreparationMillis = null;
        } else if (!['capture_preparing','listening',null].includes(stage)) {
          clearRound();
        }
        stage = next; return result();
      }
      if (next === 'transcribing' && stage === 'listening') {
        summary = null; recognitionStart = now; stage = next; return null;
      }
      if (next === 'requesting' && stage === 'transcribing') {
        transcriptionMillis = now-recognitionStart; requestStart = now; stage = next; return null;
      }
      if (next === 'speech_preparing' && stage === 'requesting') {
        requestMillis = now-requestStart; preparationStart = now; stage = next; return null;
      }
      if (next === 'playback' && stage === 'speech_preparing') {
        speechPreparationMillis = now-preparationStart; playbackStart = now; stage = next; return null;
      }
      clearRound(); blocked = true; return null;
    };
    return Object.freeze({observe, summary: result, reset});
  };
})(typeof window === 'undefined' ? globalThis : window);
