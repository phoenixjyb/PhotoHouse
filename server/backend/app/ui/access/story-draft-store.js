/* Device-local encrypted storage for explicitly saved story drafts. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.PhotoHouseStoryDraftStore = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  const DB_NAME = 'photohouse-story-drafts-v1';
  const DB_VERSION = 1;
  const STORE_NAME = 'records';
  const KEY_ID = 'encryption-key';
  const MAX_SLOTS = 20;
  const MAX_PAYLOAD_BYTES = 128 * 1024;
  const MAX_PAYLOAD_DEPTH = 64;
  const MAX_PAYLOAD_NODES = 10000;
  const MAX_SCOPE_BYTES = 1024;
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

  class StoryDraftStoreError extends Error {
    constructor(code, message, cause) {
      super(message);
      this.name = 'StoryDraftStoreError';
      this.code = code;
      if (cause !== undefined) this.cause = cause;
    }
  }

  function error(code, message, cause) {
    return new StoryDraftStoreError(code, message, cause);
  }

  function asError(value, fallback) {
    return value instanceof Error ? value : error('storage', fallback || 'Draft storage failed');
  }

  function textEncoder() {
    if (typeof TextEncoder !== 'function') throw error('crypto-unavailable', 'Secure draft storage is unavailable');
    return new TextEncoder();
  }

  function utf8(value) {
    return textEncoder().encode(value);
  }

  function byteLength(value) {
    return utf8(value).byteLength;
  }

  function validateScopePart(value, field) {
    if (typeof value !== 'string' || value.length === 0 || byteLength(value) > MAX_SCOPE_BYTES) {
      throw error('scope-invalid', `${field} must be a non-empty bounded string`);
    }
    return value;
  }

  function validateOrigin(origin) {
    if (typeof origin !== 'string' || origin.length === 0 || byteLength(origin) > 2048) {
      throw error('scope-invalid', 'origin must be an exact origin string');
    }
    let parsed;
    try { parsed = new URL(origin); } catch (cause) {
      throw error('scope-invalid', 'origin must be an exact origin string', cause);
    }
    if (parsed.origin !== origin || parsed.origin === 'null') {
      throw error('scope-invalid', 'origin must be an exact origin string');
    }
    return origin;
  }

  function validatePayload(value, { serialize = true } = {}) {
    const active = new Set();
    let nodes = 0;
    let stringUnits = 0;
    function accountForString(value) {
      stringUnits += value.length;
      if (stringUnits > MAX_PAYLOAD_BYTES * 2) throw error('payload-too-large', 'Draft payload exceeds 128 KiB');
    }
    function visit(item, depth) {
      nodes += 1;
      if (nodes > MAX_PAYLOAD_NODES) throw error('payload-invalid', 'Draft payload contains too many values');
      if (depth > MAX_PAYLOAD_DEPTH) throw error('payload-invalid', 'Draft payload is nested too deeply');
      if (item === null || typeof item === 'boolean') return;
      if (typeof item === 'string') { accountForString(item); return; }
      if (typeof item === 'number') {
        if (!Number.isFinite(item)) throw error('payload-invalid', 'Draft payload must contain finite JSON numbers');
        return;
      }
      if (typeof item !== 'object') throw error('payload-invalid', 'Draft payload must be plain JSON data');
      if (active.has(item)) throw error('payload-invalid', 'Draft payload cannot contain cycles');
      const isArray = Array.isArray(item);
      if (!isArray && Object.getPrototypeOf(item) !== Object.prototype && Object.getPrototypeOf(item) !== null) {
        throw error('payload-invalid', 'Draft payload must use plain objects and arrays');
      }
      active.add(item);
      const symbols = Object.getOwnPropertySymbols(item);
      if (symbols.length) throw error('payload-invalid', 'Draft payload cannot contain symbol properties');
      if (isArray) {
        const own = Object.getOwnPropertyNames(item).filter(name => name !== 'length');
        if (own.length > MAX_PAYLOAD_NODES) throw error('payload-invalid', 'Draft payload contains too many values');
        if (own.length !== item.length) throw error('payload-invalid', 'Draft arrays cannot contain holes or extra properties');
        for (let i = 0; i < item.length; i += 1) {
          const descriptor = Object.getOwnPropertyDescriptor(item, String(i));
          if (!descriptor || !descriptor.enumerable || !Object.prototype.hasOwnProperty.call(descriptor, 'value')) {
            throw error('payload-invalid', 'Draft payload cannot contain accessors');
          }
          visit(descriptor.value, depth + 1);
        }
      } else {
        const keys = Object.getOwnPropertyNames(item);
        if (keys.length > MAX_PAYLOAD_NODES) throw error('payload-invalid', 'Draft payload contains too many values');
        for (const key of keys) {
          accountForString(key);
          const descriptor = Object.getOwnPropertyDescriptor(item, key);
          if (!descriptor.enumerable || !Object.prototype.hasOwnProperty.call(descriptor, 'value')) {
            throw error('payload-invalid', 'Draft payload cannot contain hidden properties or accessors');
          }
          visit(descriptor.value, depth + 1);
        }
      }
      active.delete(item);
    }
    visit(value, 0);
    if (!serialize) return;
    let json;
    try { json = JSON.stringify(value); } catch (cause) {
      throw error('payload-invalid', 'Draft payload could not be serialized', cause);
    }
    if (typeof json !== 'string') throw error('payload-invalid', 'Draft payload must be JSON serializable');
    const bytes = utf8(json);
    if (bytes.byteLength > MAX_PAYLOAD_BYTES) throw error('payload-too-large', 'Draft payload exceeds 128 KiB');
    return { bytes };
  }

  function requestResult(request, ready, fail) {
    request.onsuccess = () => ready(request.result);
    request.onerror = () => fail(asError(request.error, 'IndexedDB request failed'));
  }

  function transact(db, mode, run) {
    return new Promise((resolve, reject) => {
      let tx;
      let value;
      let failure = null;
      try { tx = db.transaction(STORE_NAME, mode); } catch (cause) {
        reject(asError(cause));
        return;
      }
      const fail = cause => {
        if (failure) return;
        failure = asError(cause);
        try { tx.abort(); } catch (_) { reject(failure); }
      };
      tx.oncomplete = () => resolve(value);
      tx.onabort = () => reject(failure || asError(tx.error, 'IndexedDB transaction aborted'));
      tx.onerror = () => { /* onabort supplies the final transaction error */ };
      try {
        run(tx.objectStore(STORE_NAME), result => { value = result; }, fail);
      } catch (cause) { fail(cause); }
    });
  }

  function openDatabase(indexedDB) {
    if (!indexedDB || typeof indexedDB.open !== 'function') {
      return Promise.reject(error('storage-unavailable', 'IndexedDB is unavailable'));
    }
    return new Promise((resolve, reject) => {
      let request;
      try { request = indexedDB.open(DB_NAME, DB_VERSION); } catch (cause) {
        reject(asError(cause));
        return;
      }
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) db.createObjectStore(STORE_NAME, { keyPath: 'id' });
      };
      request.onsuccess = () => {
        request.result.onversionchange = () => request.result.close();
        resolve(request.result);
      };
      request.onerror = () => reject(asError(request.error, 'Could not open draft storage'));
      request.onblocked = () => reject(error('storage-blocked', 'Draft storage upgrade is blocked'));
    });
  }

  function validKey(key) {
    return Boolean(key && key.type === 'secret' && key.extractable === false && key.algorithm &&
      key.algorithm.name === 'AES-GCM' && Array.isArray(key.usages) &&
      key.usages.includes('encrypt') && key.usages.includes('decrypt'));
  }

  function validateStoredKey(record) {
    if (!record || record.id !== KEY_ID || !validKey(record.key)) {
      throw error('corrupt-key', 'Draft encryption key is missing or corrupt');
    }
    return record.key;
  }

  function validateStoredDraft(record) {
    if (!record || record.kind !== 'draft' || typeof record.id !== 'string' ||
        !UUID.test(record.revision || '') || !(record.iv instanceof ArrayBuffer) || record.iv.byteLength !== 12 ||
        !(record.ciphertext instanceof ArrayBuffer) || record.ciphertext.byteLength < 16 ||
        record.ciphertext.byteLength > MAX_PAYLOAD_BYTES + 16 ||
        !Number.isSafeInteger(record.payloadBytes) || record.payloadBytes < 0 || record.payloadBytes > MAX_PAYLOAD_BYTES) {
      throw error('corrupt-record', 'Encrypted draft record is corrupt');
    }
    return record;
  }

  function revision(crypto) {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  function validateCrypto(crypto) {
    if (!crypto || !crypto.subtle || typeof crypto.getRandomValues !== 'function') {
      throw error('crypto-unavailable', 'Secure draft storage requires Web Crypto');
    }
  }

  async function makeScope(crypto, origin, scope) {
    if (!scope || typeof scope !== 'object') throw error('scope-invalid', 'Draft account and library are required');
    const account = validateScopePart(scope.account, 'account');
    const library = validateScopePart(scope.library, 'library');
    const aad = utf8(JSON.stringify(['PhotoHouseStoryDraft-v1', origin, account, library]));
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', aad));
    const id = `draft:${Array.from(digest, byte => byte.toString(16).padStart(2, '0')).join('')}`;
    return { id, aad };
  }

  function countDrafts(rows) {
    // Count every non-key slot, including malformed entries, so corruption cannot
    // be used to exceed the global bound or be overwritten silently.
    return rows.filter(row => row && row.id !== KEY_ID).length;
  }

  async function create(options = {}) {
    const indexedDB = options.indexedDB === undefined ? globalThis.indexedDB : options.indexedDB;
    const crypto = options.crypto === undefined ? globalThis.crypto : options.crypto;
    const currentOrigin = options.origin === undefined ? globalThis.location && globalThis.location.origin : options.origin;
    if (globalThis.isSecureContext === false) throw error('crypto-unavailable', 'Secure draft storage requires a secure browser context');
    validateCrypto(crypto);
    const origin = validateOrigin(currentOrigin);
    const db = await openDatabase(indexedDB);

    async function readKeyAndRows(createIfEmpty) {
      // Candidate generation stays outside the transaction; the read/write
      // transaction serializes first-use across tabs before a single key wins.
      const candidate = createIfEmpty ? await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']) : null;
      return transact(db, createIfEmpty ? 'readwrite' : 'readonly', (store, done, fail) => {
        let keyRecord, rows, ready = 0;
        const finish = () => {
          if (++ready !== 2) return;
          try {
            if (keyRecord) {
              done({ key: validateStoredKey(keyRecord), rows });
              return;
            }
            if (countDrafts(rows) > 0) throw error('missing-key', 'Encrypted drafts exist but their key is missing');
            if (!createIfEmpty) { done({ key: null, rows }); return; }
            const newRecord = { id: KEY_ID, kind: 'key', key: candidate };
            store.put(newRecord);
            done({ key: candidate, rows });
          } catch (cause) { fail(cause); }
        };
        requestResult(store.get(KEY_ID), value => { keyRecord = value; finish(); }, fail);
        requestResult(store.getAll(), value => { rows = value; finish(); }, fail);
      });
    }

    async function load(scope) {
      const slot = await makeScope(crypto, origin, scope);
      const state = await readKeyAndRows(false);
      if (!state.key) return null;
      const record = state.rows.find(row => row && row.id === slot.id);
      if (!record) return null;
      validateStoredDraft(record);
      let plaintext;
      try {
        plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: new Uint8Array(record.iv), additionalData: slot.aad, tagLength: 128 }, state.key, record.ciphertext);
      } catch (cause) { throw error('corrupt-record', 'Encrypted draft could not be authenticated', cause); }
      let decodedText;
      try {
        if (plaintext.byteLength !== record.payloadBytes) throw error('corrupt-record', 'Encrypted draft size metadata does not match');
        decodedText = new TextDecoder().decode(plaintext);
        const payload = JSON.parse(decodedText);
        validatePayload(payload, { serialize: false });
        return { revision: record.revision, payload };
      } catch (cause) { throw error('corrupt-record', 'Decrypted draft payload is corrupt', cause); }
      finally {
        if (plaintext) new Uint8Array(plaintext).fill(0);
        decodedText = null;
      }
    }

    async function put(scope, payload, { expectedRevision = null } = {}) {
      if (expectedRevision !== null && (typeof expectedRevision !== 'string' || !UUID.test(expectedRevision))) {
        throw error('revision-invalid', 'Expected revision must be a UUID or null');
      }
      const slot = await makeScope(crypto, origin, scope);
      const serialized = validatePayload(payload);
      let state, iv, ciphertext;
      try {
        state = await readKeyAndRows(true);
        iv = crypto.getRandomValues(new Uint8Array(12));
        try {
          ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv, additionalData: slot.aad, tagLength: 128 }, state.key, serialized.bytes);
        } catch (cause) { throw error('crypto-failed', 'Draft encryption failed', cause); }
      } finally { serialized.bytes.fill(0); }
      const next = {
        id: slot.id,
        kind: 'draft',
        revision: revision(crypto),
        iv: iv.buffer,
        ciphertext,
        payloadBytes: serialized.bytes.byteLength,
      };
      return transact(db, 'readwrite', (store, done, fail) => {
        let keyRecord, existing, rows, ready = 0;
        const finish = () => {
          if (++ready !== 3) return;
          try {
            validateStoredKey(keyRecord);
            if (existing) validateStoredDraft(existing);
            if (expectedRevision === null ? Boolean(existing) : !existing || existing.revision !== expectedRevision) {
              throw error('conflict', 'Draft changed since it was loaded');
            }
            if (!existing && countDrafts(rows) >= MAX_SLOTS) throw error('capacity', 'All twenty local draft slots are in use');
            store.put(next);
            done({ revision: next.revision, payload });
          } catch (cause) { fail(cause); }
        };
        requestResult(store.get(KEY_ID), value => { keyRecord = value; finish(); }, fail);
        requestResult(store.get(slot.id), value => { existing = value; finish(); }, fail);
        requestResult(store.getAll(), value => { rows = value; finish(); }, fail);
      });
    }

    async function remove(scope, { expectedRevision } = {}) {
      if (typeof expectedRevision !== 'string' || !UUID.test(expectedRevision)) {
        throw error('revision-invalid', 'Deleting a draft requires its loaded revision');
      }
      const slot = await makeScope(crypto, origin, scope);
      return transact(db, 'readwrite', (store, done, fail) => {
        let keyRecord, existing, rows, ready = 0;
        const finish = () => {
          if (++ready !== 3) return;
          try {
            if (!keyRecord) {
              if (countDrafts(rows)) throw error('missing-key', 'Encrypted drafts exist but their key is missing');
              throw error('conflict', 'Draft no longer exists');
            }
            validateStoredKey(keyRecord);
            if (existing) validateStoredDraft(existing);
            if (!existing || existing.revision !== expectedRevision) throw error('conflict', 'Draft changed since it was loaded');
            store.delete(slot.id);
            done(true);
          } catch (cause) { fail(cause); }
        };
        requestResult(store.get(KEY_ID), value => { keyRecord = value; finish(); }, fail);
        requestResult(store.get(slot.id), value => { existing = value; finish(); }, fail);
        requestResult(store.getAll(), value => { rows = value; finish(); }, fail);
      });
    }

    return Object.freeze({ load, put, remove, close() { db.close(); } });
  }

  return Object.freeze({ create, StoryDraftStoreError, limits: Object.freeze({ maxSlots: MAX_SLOTS, maxPayloadBytes: MAX_PAYLOAD_BYTES }) });
});
