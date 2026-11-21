// Página Transcribir: origen, modelos, cola, editor de frases y exportación.
'use strict';
(() => {
  const { invoke, esc, toast, queue, renderQueue, showPage, fmtTime } = window.MXP;
  const T = window.__TAURI__;
  const root = document.getElementById('transcribe-root');
  root.classList.remove('panel');

  const FORMATS = [['txt', 'Texto (TXT)'], ['docx', 'Word (DOCX)'], ['pdf', 'PDF'], ['srt', 'Subtítulos SRT'], ['vtt', 'Subtítulos VTT'],
    ['md', 'Markdown'], ['html', 'HTML interactivo'], ['json', 'JSON'], ['csv', 'CSV (Excel)'], ['tsv', 'TSV'], ['lrc', 'Letras LRC']];
  const SUBTITLE_FORMATS = ['srt', 'vtt', 'lrc'];

  root.innerHTML = `
    <div class="urlbar" style="margin-top:0">
      <div class="field"><input class="input" id="tr-source" placeholder="Arrastra aquí un audio o video, o pega un enlace" spellcheck="false"></div>
      <button class="btn" id="tr-pick"><i class="i sm" style="--i:url(icons/folder-open.png)"></i>Elegir archivo</button>
    </div>
    <div class="options">
      <label><span class="tiny-label">Modelo</span><select class="input" id="tr-model"></select></label>
      <label><span class="tiny-label">Idioma</span><select class="input" id="tr-lang"></select></label>
      <label><span class="tiny-label">Vocabulario (opcional)</span><input class="input" id="tr-prompt" placeholder="Nombres propios, marcas…" style="height:34px;width:220px"></label>
      <label class="row" style="margin-top:16px;gap:6px"><input type="checkbox" id="tr-translate"> Traducir al inglés</label>
    </div>
    <div class="row spread" style="margin-top:16px">
      <button class="chip" id="tr-models-toggle"><i class="i sm" style="--i:url(icons/cpu.png)"></i>Gestionar modelos</button>
      <button class="btn primary" id="tr-go"><i class="i sm" style="--i:url(icons/microphone.png)"></i>Transcribir</button>
    </div>
    <div class="panel" id="tr-models" hidden></div>
    <div id="tr-result" hidden>
      <div class="row spread" style="margin-top:22px">
        <div><div class="label" id="tr-title"></div><div class="hint" id="tr-meta"></div></div>
        <button class="btn" id="tr-copy"><i class="i sm" style="--i:url(icons/copy.png)"></i>Copiar texto</button>
      </div>
      <p class="hint">Puedes corregir cualquier frase: haz clic en ella y escribe. Lo que cambies se usa al exportar.</p>
      <div class="editor" id="tr-editor"></div>
      <div class="row" style="margin-top:12px;flex-wrap:wrap">
        <select class="input" id="tr-format"></select>
        <select class="input" id="tr-gran">
          <option value="">Tiempos: automático</option><option value="paragraph">Por párrafo</option>
          <option value="sentence">Por frase</option><option value="word">Por palabra</option><option value="subtitle">Por subtítulo</option>
        </select>
        <label class="row" style="gap:6px"><input type="checkbox" id="tr-stamps" checked> Con marcas de tiempo</label>
        <button class="btn primary" id="tr-export"><i class="i sm" style="--i:url(icons/file-export.png)"></i>Exportar</button>
      </div>
    </div>`;

  const $ = (s) => root.querySelector(s);
  $('#tr-format').innerHTML = FORMATS.map(([v, l]) => `<option value="${v}">${l}</option>`).join('');

  // ── Modelos ──
  let models = [];
  const dl = {}; // key → { done, total }
  const size = (b) => (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.round(b / 1e6)} MB`);

  async function loadModels() {
    models = await invoke('models_list');
    const installed = models.filter((m) => m.installed);
    const sel = $('#tr-model');
    const keep = sel.value || window.MXP.settings.transcribe_model || 'turbo-q5';
    sel.innerHTML = installed.length
      ? installed.map((m) => `<option value="${m.key}">${esc(m.name)}</option>`).join('')
      : '<option value="">Ningún modelo descargado</option>';
    if (installed.some((m) => m.key === keep)) sel.value = keep;
    renderModels();
  }

  function renderModels() {
    $('#tr-models').innerHTML = `<div class="list">${models.map((m) => {
      const d = dl[m.key];
      const state = d ? `Descargando ${size(d.done)} de ${size(d.total || m.bytes)}` : m.installed ? 'Instalado' : size(m.bytes);
      const action = d ? `<button class="btn" data-cancel="${m.key}">Cancelar</button>`
        : m.installed ? `<button class="btn" data-del="${m.key}">Borrar</button>`
          : `<button class="btn" data-get="${m.key}">Descargar</button>`;
      return `<div class="item"><div class="grow"><div class="t">${esc(m.name)}${m.key === 'turbo-q5' ? ' <span class="tag">Recomendado</span>' : ''}</div>
        <div class="d">${esc(m.description)} · ${esc(state)}</div></div>${action}</div>`;
    }).join('')}</div>`;
  }

  $('#tr-models').onclick = async (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.get) { dl[b.dataset.get] = { done: 0, total: 0 }; renderModels(); invoke('model_download', { key: b.dataset.get }); }
    if (b.dataset.cancel) invoke('model_cancel', { key: b.dataset.cancel });
    if (b.dataset.del && confirm('¿Borrar este modelo? Podrás volver a descargarlo cuando quieras.')) {
      await invoke('model_delete', { key: b.dataset.del });
      loadModels();
    }
  };
  T.event.listen('model', ({ payload: m }) => {
    if (m.status === 'downloading') dl[m.key] = { done: m.done, total: m.total };
    else {
      delete dl[m.key];
      if (m.status === 'error') toast(`No se pudo descargar el modelo: ${m.error}`, 8000);
      if (m.status === 'done') toast('Modelo listo para usar.');
      loadModels();
    }
    renderModels();
  });
  $('#tr-models-toggle').onclick = () => {
    const p = $('#tr-models');
    p.hidden = !p.hidden;
    $('#tr-models-toggle').classList.toggle('on', !p.hidden);
  };

  // ── Lanzar ──
  async function transcribe(source) {
    source = (source || '').trim();
    if (!source) { toast('Elige un archivo o pega un enlace.'); return; }
    const model = $('#tr-model').value;
    if (!model) {
      showPage('transcribe');
      $('#tr-models').hidden = false;
      toast('Descarga primero un modelo (el recomendado va bien en casi cualquier PC).', 6000);
      return;
    }
    const s = window.MXP.settings;
    s.transcribe_model = model;
    s.transcribe_language = $('#tr-lang').value;
    window.MXP.saveSettings();
    const options = {
      source, model, language: $('#tr-lang').value, translate: $('#tr-translate').checked, prompt: $('#tr-prompt').value,
      cookies_browser: s.cookies_browser && s.cookies_browser !== 'ninguno' ? s.cookies_browser : null,
      cookies_file: s.cookies_file || null,
    };
    const job = { kind: 'transcribe', state: 'running', percent: 0, title: source.split(/[\\/]/).pop(), message: 'Preparando…', options };
    job.onView = () => { showPage('transcribe'); showResult(job); };
    job.onRetry = () => start(job);
    queue.push(job);
    start(job);
  }

  async function start(job) {
    job.state = 'running'; job.percent = 0; job.message = 'Preparando…';
    renderQueue();
    job.jobId = await invoke('transcribe_start', { options: job.options });
  }

  T.event.listen('transcribe', ({ payload: p }) => {
    const job = queue.find((j) => j.kind === 'transcribe' && j.jobId === p.id);
    if (!job) return;
    job.percent = p.percent;
    job.message = p.message;
    if (p.status === 'done') {
      Object.assign(job, { state: 'done', result: p, title: p.source || job.title });
      window.MXP.notify('Transcripción lista', job.title);
      if (!document.querySelector('section[data-page="transcribe"]').hidden) showResult(job);
    } else if (p.status === 'error') {
      Object.assign(job, { state: 'failed', error: { message: p.message, hint: '' } });
    } else if (p.status === 'cancelled') job.state = 'cancelled';
    renderQueue();
  });

  // ── Resultado y editor ──
  let current = null;
  function showResult(job) {
    current = job;
    const r = job.result;
    $('#tr-result').hidden = false;
    $('#tr-title').textContent = r.source;
    $('#tr-meta').textContent = `Idioma: ${r.language} · ${fmtTime(r.duration)} · ${r.sentences.length} frases`;
    $('#tr-editor').innerHTML = r.sentences.map((s, i) =>
      `<div class="sent"><time>${esc(fmtTime(s.start))}</time><span contenteditable="plaintext-only" spellcheck="true" data-i="${i}">${esc(s.text)}</span></div>`).join('');
  }
  const editedTexts = () => [...$('#tr-editor').querySelectorAll('[data-i]')].map((el) => el.textContent.replace(/\s+/g, ' ').trim());

  $('#tr-copy').onclick = () => navigator.clipboard.writeText(editedTexts().join(' ')).then(() => toast('Texto copiado'));
  $('#tr-format').onchange = () => { $('#tr-gran').value = ''; };
  $('#tr-export').onclick = async () => {
    if (!current) return;
    const fmt = $('#tr-format').value;
    const base = (current.result.source || 'transcripción').replace(/\.[^.]+$/, '').replace(/[\\/:*?"<>|]/g, '_');
    const path = await T.dialog.save({ defaultPath: `${base}.${fmt}`, filters: [{ name: fmt.toUpperCase(), extensions: [fmt] }] });
    if (!path) return;
    try {
      await invoke('transcribe_export', {
        id: current.jobId, format: fmt, path,
        granularity: $('#tr-gran').value || null,
        stamps: SUBTITLE_FORMATS.includes(fmt) || $('#tr-stamps').checked,
        edits: editedTexts(),
      });
      toast('Exportado.');
      T.opener.revealItemInDir(path).catch(() => {});
    } catch (e) { toast(`No se pudo exportar: ${e}`, 8000); }
  };

  // ── Origen: botón, arrastrar y soltar ──
  $('#tr-pick').onclick = async () => {
    const f = await T.dialog.open({ filters: [{ name: 'Audio y video', extensions: ['mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg', 'opus', 'wma', 'mp4', 'mkv', 'mov', 'webm', 'avi', 'wmv', 'm4v', 'mpg', 'mpeg', '3gp'] }] });
    if (f) $('#tr-source').value = f;
  };
  $('#tr-go').onclick = () => transcribe($('#tr-source').value);
  window.addEventListener('mxp:drop', (e) => {
    if (!document.querySelector('section[data-page="transcribe"]').hidden) $('#tr-source').value = e.detail[0];
  });

  window.MXP.transcribe = (src) => { showPage('transcribe'); transcribe(src); };

  // ── Arranque ──
  (async () => {
    const langs = await invoke('transcribe_languages');
    $('#tr-lang').innerHTML = langs.map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join('');
    $('#tr-lang').value = window.MXP.settings.transcribe_language || 'auto';
    loadModels();
  })();
})();
