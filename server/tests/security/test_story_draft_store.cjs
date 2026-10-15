"use strict";
/* Exercises encrypted draft storage in a real secure browser origin and IndexedDB. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');

const modulePath = path.resolve(__dirname, '../../backend/app/ui/access/story-draft-store.js');
const browserArgs = ['--disable-background-networking', '--disable-component-update', '--no-first-run', '--host-resolver-rules=MAP * ~NOTFOUND'];
const scopeA = { account: 'acct-01', library: 'family-01' };
const payload = { title: 'A private family story', chapters: [{ text: '河边的夏天' }], assetIds: ['asset-1'] };
const pass = label => console.log('PASS ' + label);

async function configurePage(context, url) {
  await context.route('**/*', route => route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><meta charset="utf-8"><title>draft store check</title>' }));
  const page = await context.newPage();
  await page.goto(url);
  await page.addScriptTag({ path: modulePath });
  await page.evaluate(() => {
    window.makeDraftStore = origin => window.PhotoHouseStoryDraftStore.create({ origin: origin || location.origin });
    window.scopeDigest = async (origin, account, library) => {
      const aad = new TextEncoder().encode(JSON.stringify(['PhotoHouseStoryDraft-v1', origin, account, library]));
      const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', aad));
      return 'draft:' + Array.from(digest, byte => byte.toString(16).padStart(2, '0')).join('');
    };
    window.openRecords = () => new Promise((resolve, reject) => {
      const request = indexedDB.open('photohouse-story-drafts-v1', 1);
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
    });
    window.allRecords = async () => {
      const db = await openRecords();
      return new Promise((resolve, reject) => {
        const tx = db.transaction('records', 'readonly');
        const req = tx.objectStore('records').getAll();
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
        tx.oncomplete = () => db.close();
      });
    };
    window.editRecord = async (id, edit) => {
      const db = await openRecords();
      return new Promise((resolve, reject) => {
        const tx = db.transaction('records', 'readwrite');
        const store = tx.objectStore('records');
        const req = store.get(id);
        req.onsuccess = () => { try { edit(store, req.result); } catch (error) { tx.abort(); reject(error); } };
        req.onerror = () => reject(req.error);
        tx.oncomplete = () => { db.close(); resolve(); };
        tx.onabort = () => { db.close(); if (tx.error) reject(tx.error); };
      });
    };
  });
  return page;
}

async function main() {
  const browser = await chromium.launch({ headless: true, ...(process.env.PH_BROWSER_EXECUTABLE ? { executablePath: process.env.PH_BROWSER_EXECUTABLE } : {}), args: browserArgs });
  try {
    const context = await browser.newContext({ ignoreHTTPSErrors: true, serviceWorkers: 'block' });
    const page = await configurePage(context, 'https://draft-store.test/');
    assert.equal(await page.evaluate(() => isSecureContext), true);

    const stored = await page.evaluate(async ({ scope, data }) => {
      const store = await makeDraftStore();
      const result = await store.put(scope, data);
      return { result, first: await store.load(scope), hidden: await store.load({ account: 'other-account', library: scope.library }) };
    }, { scope: scopeA, data: payload });
    assert.match(stored.result.revision, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
    assert.deepEqual(stored.first, stored.result);
    assert.equal(stored.hidden, null);
    const rowDump = await page.evaluate(async () => JSON.stringify(await allRecords(), (_key, value) => value instanceof ArrayBuffer ? Array.from(new Uint8Array(value)) : value));
    assert.equal(rowDump.includes(payload.title), false);
    assert.equal(rowDump.includes(payload.chapters[0].text), false);
    assert.equal(rowDump.includes(scopeA.account), false);
    assert.equal(rowDump.includes(scopeA.library), false);
    const keyState = await page.evaluate(async () => {
      const key = (await allRecords()).find(item => item.id === 'encryption-key').key;
      let exportRejected = false;
      try { await crypto.subtle.exportKey('raw', key); } catch (_) { exportRejected = true; }
      return { extractable: key.extractable, exportRejected };
    });
    assert.deepEqual(keyState, { extractable: false, exportRejected: true });
    pass('Draft bytes and scope identifiers are not stored as plaintext; account isolation holds');

    const moved = await page.evaluate(async ({ from, to }) => {
      const origin = location.origin;
      const oldId = await scopeDigest(origin, from.account, from.library);
      const newId = await scopeDigest(origin, to.account, to.library);
      await editRecord(oldId, (store, row) => { store.delete(oldId); store.put({ ...row, id: newId }); });
      try { await (await makeDraftStore()).load(to); } catch (error) { return error.code; }
      return 'unexpected-success';
    }, { from: scopeA, to: { account: 'acct-02', library: 'family-01' } });
    assert.equal(moved, 'corrupt-record');
    pass('Moving ciphertext to another scope fails authenticated decryption');

    // Restore the primary slot so the CAS and deletion checks run against a
    // legitimate record. This moves the same ciphertext back without decrypting.
    await page.evaluate(async ({ from, to }) => {
      const oldId = await scopeDigest(location.origin, from.account, from.library);
      const movedId = await scopeDigest(location.origin, to.account, to.library);
      await editRecord(movedId, (store, row) => { store.delete(movedId); store.put({ ...row, id: oldId }); });
    }, { from: scopeA, to: { account: 'acct-02', library: 'family-01' } });

    const cas = await page.evaluate(async ({ scope, data }) => {
      const a = await makeDraftStore(), b = await makeDraftStore();
      const attempts = await Promise.allSettled([a.put(scope, { ...data, writer: 'a' }), b.put(scope, { ...data, writer: 'b' })]);
      const winners = attempts.filter(item => item.status === 'fulfilled');
      const losers = attempts.filter(item => item.status === 'rejected' && item.reason.code === 'conflict');
      const loaded = await a.load(scope);
      const updates = await Promise.allSettled([
        a.put(scope, { ...loaded.payload, update: 'a' }, { expectedRevision: loaded.revision }),
        b.put(scope, { ...loaded.payload, update: 'b' }, { expectedRevision: loaded.revision }),
      ]);
      return { winners: winners.length, losers: losers.length, updates: updates.map(item => item.status === 'fulfilled' ? 'fulfilled' : item.reason.code), loaded: await a.load(scope) };
    }, { scope: { account: 'cas-account', library: 'cas-library' }, data: payload });
    assert.equal(cas.winners, 1);
    assert.equal(cas.losers, 1);
    assert.deepEqual(cas.updates.sort(), ['conflict', 'fulfilled']);
    assert(cas.loaded.revision);
    pass('Concurrent first insert and stale update each have a single compare-and-swap winner');

    const quota = await page.evaluate(async ({ scope, data }) => {
      const store = await makeDraftStore();
      const prior = await store.load(scope);
      const descriptor = Object.getOwnPropertyDescriptor(IDBObjectStore.prototype, 'put');
      IDBObjectStore.prototype.put = function (value, key) {
        if (value && value.kind === 'draft') throw new DOMException('Synthetic quota exhaustion', 'QuotaExceededError');
        return descriptor.value.call(this, value, key);
      };
      let code;
      try { await store.put(scope, { ...data, changed: true }, { expectedRevision: prior.revision }); }
      catch (error) { code = error.name; }
      finally { Object.defineProperty(IDBObjectStore.prototype, 'put', descriptor); }
      return { code, after: await store.load(scope) };
    }, { scope: { account: 'cas-account', library: 'cas-library' }, data: payload });
    assert.equal(quota.code, 'QuotaExceededError');
    assert.equal(quota.after.payload.changed, undefined);
    pass('Quota failure rejects the write and leaves the prior encrypted draft intact');

    const deletions = await page.evaluate(async ({ scope, data }) => {
      const store = await makeDraftStore();
      const current = await store.load(scope);
      let stale;
      try { await store.remove(scope, { expectedRevision: '00000000-0000-4000-8000-000000000000' }); }
      catch (error) { stale = error.code; }
      const removed = await store.remove(scope, { expectedRevision: current.revision });
      let absent;
      try { await store.remove(scope, { expectedRevision: current.revision }); }
      catch (error) { absent = error.code; }
      return { stale, removed, absent, loaded: await store.load(scope) };
    }, { scope: { account: 'cas-account', library: 'cas-library' }, data: payload });
    assert.equal(deletions.stale, 'conflict');
    assert.equal(deletions.removed, true);
    assert.equal(deletions.absent, 'conflict');
    assert.equal(deletions.loaded, null);
    pass('Delete requires the currently loaded revision and cannot erase a newer record');

    const corruptContext = await browser.newContext({ ignoreHTTPSErrors: true, serviceWorkers: 'block' });
    const corruptPage = await configurePage(corruptContext, 'https://corrupt-draft.test/');
    const corrupted = await corruptPage.evaluate(async () => {
      const store = await makeDraftStore();
      const scope = { account: 'corrupt-account', library: 'corrupt-library' };
      await store.put(scope, { privateText: 'must remain encrypted' });
      const row = (await allRecords()).find(item => item.kind === 'draft');
      const originalCiphertext = row.ciphertext;
      await editRecord(row.id, (objectStore, current) => objectStore.put({ ...current, ciphertext: new ArrayBuffer(128 * 1024 + 17) }));
      let oversized;
      try { await store.load(scope); } catch (error) { oversized = error.code; }
      await editRecord(row.id, (objectStore, current) => objectStore.put({ ...current, ciphertext: originalCiphertext }));
      const bytes = new Uint8Array(row.ciphertext); bytes[0] ^= 1;
      await editRecord(row.id, (objectStore, current) => objectStore.put({ ...current, ciphertext: bytes.buffer }));
      let corrupt;
      try { await store.load(scope); } catch (error) { corrupt = error.code; }
      const keyId = 'encryption-key';
      await editRecord(keyId, objectStore => objectStore.delete(keyId));
      let missingKey;
      try { await store.load(scope); } catch (error) { missingKey = error.code; }
      let putMissingKey;
      try { await store.put({ account: 'another-account', library: 'corrupt-library' }, { text: 'never stored' }); }
      catch (error) { putMissingKey = error.code; }
      const keyRecreated = (await allRecords()).some(item => item.id === keyId);
      return { oversized, corrupt, missingKey, putMissingKey, keyRecreated };
    });
    assert.deepEqual(corrupted, { oversized: 'corrupt-record', corrupt: 'corrupt-record', missingKey: 'missing-key', putMissingKey: 'missing-key', keyRecreated: false });
    pass('Oversized or corrupt ciphertext and a missing key with surviving records fail visibly');
    await corruptContext.close();

    const capacityContext = await browser.newContext({ ignoreHTTPSErrors: true, serviceWorkers: 'block' });
    const capacityPage = await configurePage(capacityContext, 'https://capacity-draft.test/');
    const bounds = await capacityPage.evaluate(async () => {
      const store = await makeDraftStore();
      const deep = {}; let cursor = deep;
      for (let i = 0; i < 65; i += 1) { cursor.next = {}; cursor = cursor.next; }
      let deepCode;
      try { await store.put({ account: 'deep', library: 'library' }, deep); }
      catch (error) { deepCode = error.code; }
      for (let i = 0; i < 20; i += 1) await store.put({ account: 'account-' + i, library: 'library' }, { n: i });
      let code;
      try { await store.put({ account: 'account-20', library: 'library' }, { n: 20 }); }
      catch (error) { code = error.code; }
      let large;
      try { await store.put({ account: 'large', library: 'library' }, { text: 'x'.repeat(128 * 1024) }); }
      catch (error) { large = error.code; }
      return { code, large, deepCode, lastExisting: await store.load({ account: 'account-19', library: 'library' }) };
    });
    assert.equal(bounds.code, 'capacity');
    assert.equal(bounds.large, 'payload-too-large');
    assert.equal(bounds.deepCode, 'payload-invalid');
    assert.deepEqual(bounds.lastExisting.payload, { n: 19 });
    pass('Twenty-slot and UTF-8 payload bounds reject excess without evicting stored drafts');

    await capacityContext.close();
    await context.close();
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
