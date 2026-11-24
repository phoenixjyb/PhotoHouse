'use strict';

window.PhotoHouseOralHistory = ({panel, scope, request, capture, reserveCapture, claimCapture, releaseCapture, onAuthorizationFailure}) => {
  const words = {
    en: {
      help:'Only you can open the saved recording. Record up to 20 seconds at a time. Save each section before leaving.',
      title:'Title', subject:'Who is this about?', narrator:'Who is speaking?', language:'Recording language',
      und:'Unspecified', mixed:'Mixed', retention:'I agree to keep my original recording in PhotoHouse.',
      processing:'I also allow future local transcription.',
      create:'Start a recording', record:'Record a section', stop:'Stop recording', save:'Save section',
      discard:'Discard unsaved audio', finish:'Finish recording', sections:'Saved sections · {count}',
      preview:'Listen to this unsaved section',
      loading:'Opening your recordings…', noRecordings:'You have no unfinished recordings.',
      ready:'Ready to record.', microphone:'Waiting for microphone…', recording:'Recording this section…',
      microphoneBusy:'Close the other recording before starting this one.',
      recordFailed:'No audio was captured. Check microphone access and try again.',
      review:'Save this section to keep it, or discard it and record again.',
      saving:'Saving…', saved:'Section saved.', closing:'Finishing the recording…',
      finished:'Recording finished. The saved audio stays private.',
      uncertain:'The server did not confirm this action. Try the same action again.',
      changed:'This recording has changed. Reopen this panel to check the saved sections.',
      unavailable:'Your recordings are unavailable. Reopen this panel to try again.',
    },
    zh: {
      help:'已保存的录音仅你可打开。每次最多录制 20 秒，请在离开前保存每段录音。',
      title:'标题', subject:'这段故事关于谁？', narrator:'谁在讲述？', language:'录音语言',
      und:'未指定', mixed:'混合语言', retention:'我同意在 PhotoHouse 中保留原始录音。',
      processing:'我也同意今后在本机转写。',
      create:'新建录音', record:'录制一段', stop:'停止录音', save:'保存本段',
      discard:'丢弃未保存的录音', finish:'完成录音', sections:'已保存段数 · {count}',
      preview:'试听未保存的本段录音',
      loading:'正在打开你的录音…', noRecordings:'没有未完成的录音。',
      ready:'可以开始录音。', microphone:'正在等待麦克风…', recording:'正在录制本段…',
      microphoneBusy:'请先结束其他录音。',
      recordFailed:'没有录到声音。请检查麦克风权限后重试。',
      review:'保存本段，或丢弃后重新录制。',
      saving:'正在保存…', saved:'本段已保存。', closing:'正在完成录音…',
      finished:'录音已完成。已保存的音频仍仅你可访问。',
      uncertain:'服务器尚未确认。请重试同一操作。',
      changed:'录音已发生变化。请重新打开此面板，查看已保存的段落。',
      unavailable:'暂时无法打开你的录音。请重新打开此面板重试。',
    },
  };
  const element = name => panel.querySelector('#oral-history-' + name);
  const form = element('create'), list = element('list'), status = element('status');
  const record = element('record'), stop = element('stop'), save = element('save');
  const discard = element('discard'), finish = element('finish'), active = element('active');
  const preview = element('preview');
  const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/;
  const digest = /^[0-9a-f]{64}$/;
  const maxSections = 180;
  const sectionSeconds = 20;
  const maxSectionBytes = 44 + sectionSeconds * 16000 * 2;
  let owner = null, sessions = [], session = null, task = null, recording = null, section = null;
  let pendingCreate = null, pendingFinish = null, notice = '', loaded = false;
  let previewURL = null;

  const text = key => words[scope().language === 'zh' ? 'zh' : 'en'][key] || '';
  const path = binding => '/oral-history/v1/libraries/' + encodeURIComponent(binding.library) + '/sessions';
  function current(binding) {
    const now = scope();
    return !!binding?.account && !!binding.library && binding === owner && panel.open && !document.hidden && !now.locked &&
      now.generation === binding.generation && now.account === binding.account && now.library === binding.library;
  }

  function checkedStatus(value, binding, id = value?.session_id) {
    if (value?.version !== 2 || typeof id !== 'string' || !uuid.test(id) || value.session_id !== id ||
        value.author_id !== binding.account || value.library_id !== binding.library ||
        typeof value.title !== 'string' || !value.title.trim() || value.title.length > 512 ||
        value.retention_consent !== true || typeof value.processing_consent !== 'boolean' ||
        !['open', 'completed'].includes(value.state) || !Number.isInteger(value.section_count) ||
        value.section_count < 0 || value.section_count > maxSections ||
        value.next_ordinal !== value.section_count ||
        value.revision !== 1 + value.section_count + Number(value.state === 'completed') ||
        typeof value.manifest_sha256 !== 'string' || !digest.test(value.manifest_sha256)) {
      throw new Error('Invalid recording status');
    }
    return value;
  }

  function remember(item) {
    sessions = sessions.filter(row => row.session_id !== item.session_id);
    if (item.state === 'open') sessions.unshift(item);
  }

  function renderList() {
    list.replaceChildren(...sessions.filter(item => item.session_id !== session?.session_id).map(item => {
      const row = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'quiet';
      button.textContent = item.title;
      button.addEventListener('click', () => void resume(item.session_id));
      row.append(button);
      return row;
    }));
  }

  function paint() {
    if (!current(owner)) return;
    const editing = !!session;
    form.hidden = !loaded || editing;
    list.hidden = !list.childElementCount;
    active.hidden = !editing;
    status.textContent = text(notice);
    for (const field of form.querySelectorAll('input,select')) field.disabled = !!task || !!pendingCreate;
    form.querySelector('button').disabled = !!task;
    for (const button of list.querySelectorAll('button')) {
      button.disabled = !!(task || recording || section || pendingCreate || pendingFinish);
    }
    if (!session) return;
    element('current').textContent = session.title;
    element('sections').textContent = text('sections').replace('{count}', session.section_count);
    record.hidden = !!recording || !!section || session.section_count >= maxSections;
    record.disabled = !!task || !!pendingFinish;
    stop.hidden = !recording?.handle;
    stop.disabled = recording?.handle?.stopped === true;
    save.hidden = discard.hidden = !section;
    save.disabled = discard.disabled = !!task;
    finish.disabled = !!(task || recording || section) || session.section_count === 0;
  }

  function translate() {
    for (const node of panel.querySelectorAll('[data-oral-word]')) node.textContent = text(node.dataset.oralWord);
    preview.setAttribute('aria-label', text('preview'));
    paint();
  }

  function clearSection() {
    section = null;
    preview.hidden = true;
    if (!previewURL) return;
    preview.pause();
    preview.removeAttribute('src');
    preview.load();
    URL.revokeObjectURL(previewURL);
    previewURL = null;
  }

  function clear() {
    owner = null;
    task?.abort();
    recording?.controller.abort();
    if (recording) {
      if (recording.handle) void recording.handle.stop(false).catch(() => {});
      releaseCapture(recording.reservation);
    }
    clearSection();
    task = recording = pendingCreate = pendingFinish = session = null;
    loaded = false;
    sessions = [];
    list.replaceChildren();
    form.reset();
    form.hidden = list.hidden = active.hidden = true;
    status.textContent = element('current').textContent = element('sections').textContent = '';
  }

  async function run(waiting, failed, action) {
    const binding = owner;
    if (!current(binding) || task) return;
    const controller = new AbortController();
    task = controller;
    notice = waiting;
    paint();
    const call = (suffix = '', options = {}) => request(path(binding) + suffix, {
      ...options, epoch:binding.generation, signal:controller.signal,
    });
    try {
      await action(binding, call);
    } catch (error) {
      if (current(binding) && error.name !== 'AbortError') {
        if (error.status === 401 || error.status === 403) {
          clear();
          void onAuthorizationFailure(error, binding.generation);
        } else {
          notice = error.status === 409 ? 'changed' : failed;
        }
      }
    } finally {
      if (task === controller) task = null;
      paint();
    }
  }

  function open() {
    clear();
    owner = scope();
    translate();
    return run('loading', 'unavailable', async (binding, call) => {
      const result = await call();
      if (!current(binding)) return;
      if (result?.version !== 2 || result.library_id !== binding.library ||
          !Array.isArray(result.items) || result.items.length > 8) throw new Error('Invalid recording list');
      const items = result.items.map(item => checkedStatus(item, binding));
      if (items.some(item => item.state !== 'open') ||
          new Set(items.map(item => item.session_id)).size !== items.length) throw new Error('Invalid recording list');
      sessions = items;
      loaded = true;
      notice = sessions.length ? '' : 'noRecordings';
      renderList();
    });
  }

  function resume(id) {
    if (recording || section || pendingCreate || pendingFinish) return;
    return run('loading', 'unavailable', async (binding, call) => {
      const result = await call('/' + id);
      if (!current(binding)) return;
      const restored = checkedStatus(result, binding, id);
      remember(restored);
      session = restored.state === 'open' ? restored : null;
      notice = session ? 'ready' : 'finished';
      renderList();
    });
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!current(owner) || task || !loaded || session) return;
    const fields = new FormData(form);
    if (!pendingCreate) {
      const title = String(fields.get('title') || '').trim();
      if (!title || fields.get('retention') !== 'on') return;
      pendingCreate = {
        request_id:crypto.randomUUID(), title, subject_label:String(fields.get('subject') || '').trim(),
        narrator_label:String(fields.get('narrator') || '').trim(), language:fields.get('language'),
        retention_consent:true, processing_consent:fields.get('processing') === 'on',
      };
    }
    const body = pendingCreate;
    void run('saving', 'uncertain', async (binding, call) => {
      const result = await call('', {method:'POST', body});
      if (!current(binding)) return;
      const created = checkedStatus(result, binding);
      if (created.request_id !== body.request_id || created.operation !== 'create' ||
          created.title !== body.title || created.section_count !== 0 || created.state !== 'open' ||
          created.processing_consent !== body.processing_consent) throw new Error('Invalid create receipt');
      remember(created);
      session = created;
      pendingCreate = null;
      form.reset();
      notice = 'ready';
      renderList();
    });
  });

  record.addEventListener('click', async () => {
    const binding = owner, source = session;
    if (!current(binding) || !source || task || recording || section || pendingFinish ||
        source.section_count >= maxSections) return;
    const reservation = reserveCapture();
    if (!reservation) {
      notice = 'microphoneBusy';
      paint();
      return;
    }
    const attempt = {reservation, controller:new AbortController(), handle:null};
    recording = attempt;
    notice = 'microphone';
    paint();
    const recordingCurrent = () => current(binding) && recording === attempt && session === source;
    try {
      const handle = await capture(file => {
        if (!recordingCurrent()) return;
        recording = null;
        releaseCapture(reservation);
        if (file?.type === 'audio/wav' && file.size > 44 && file.size <= maxSectionBytes) {
          section = {id:crypto.randomUUID(), audio:file, source};
          previewURL = URL.createObjectURL(file);
          preview.src = previewURL;
          preview.hidden = false;
          notice = 'review';
        } else notice = 'recordFailed';
        paint();
      }, sectionSeconds, {isCurrent:recordingCurrent, signal:attempt.controller.signal});
      if (!recordingCurrent() || !claimCapture(reservation, handle)) {
        await handle.stop(false);
        if (recordingCurrent()) throw new Error('Microphone no longer available');
        return;
      }
      attempt.handle = handle;
      notice = 'recording';
      paint();
    } catch {
      releaseCapture(reservation);
      if (recordingCurrent()) {
        recording = null;
        notice = 'recordFailed';
        paint();
      }
    }
  });

  stop.addEventListener('click', () => {
    const attempt = recording;
    if (!current(owner) || !attempt?.handle) return;
    void attempt.handle.stop(true).catch(() => {
      if (recording === attempt) {
        recording = null;
        notice = 'recordFailed';
        paint();
      }
    });
    paint();
  });

  discard.addEventListener('click', () => {
    if (!current(owner) || task) return;
    clearSection();
    notice = 'ready';
    paint();
  });

  save.addEventListener('click', () => {
    const pending = section;
    if (!pending || pending.source !== session) return;
    void run('saving', 'uncertain', async (binding, call) => {
      const bytes = new Uint8Array(await pending.audio.arrayBuffer());
      let sha256;
      try {
        const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
        sha256 = Array.from(hash, value => value.toString(16).padStart(2,'0')).join('');
      } finally {
        bytes.fill(0);
      }
      if (!current(binding)) return;
      const source = pending.source;
      const receipt = await call('/' + source.session_id + '/sections', {method:'POST', rawBody:pending.audio,
        extraHeaders:{'Content-Type':'audio/wav', 'X-PhotoHouse-Request-Id':pending.id,
          'X-PhotoHouse-Expected-Revision':String(source.revision), 'X-PhotoHouse-Ordinal':String(source.next_ordinal)}});
      if (!current(binding)) return;
      const accepted = checkedStatus(receipt, binding, source.session_id);
      if (accepted.request_id !== pending.id || accepted.operation !== 'append' ||
          accepted.ordinal !== source.next_ordinal || accepted.section_sha256 !== sha256 ||
          accepted.section_count !== source.section_count + 1 || accepted.state !== 'open') {
        throw new Error('Invalid section receipt');
      }
      session = accepted;
      remember(accepted);
      clearSection();
      notice = 'saved';
      renderList();
    });
  });

  finish.addEventListener('click', () => {
    if (!current(owner) || task || !session?.section_count || recording || section) return;
    const source = session;
    pendingFinish ??= {request_id:crypto.randomUUID(), expected_revision:source.revision};
    const body = pendingFinish;
    void run('closing', 'uncertain', async (binding, call) => {
      const result = await call('/' + source.session_id + '/complete', {method:'POST', body});
      if (!current(binding)) return;
      const closed = checkedStatus(result, binding, source.session_id);
      if (closed.request_id !== body.request_id || closed.operation !== 'complete' ||
          closed.state !== 'completed' || closed.section_count !== source.section_count) {
        throw new Error('Invalid recording completion receipt');
      }
      remember(closed);
      session = pendingFinish = null;
      notice = 'finished';
      renderList();
    });
  });

  return {open, clear, translate};
};
