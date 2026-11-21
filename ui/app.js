// MXP Suite — interfaz. Toda la lógica pesada vive en Rust; aquí solo hay
// estado de pantalla, la cola y llamadas a `invoke`.
'use strict';

const T = window.__TAURI__;
const invoke = T.core.invoke;
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];

/** Todo texto que venga de fuera (títulos de videos, errores) pasa por aquí. */
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function toast(msg, ms = 3500) {
  const t = $('#toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), ms);
}

const fmtTime = (s) => {
  if (s == null || !isFinite(s)) return '';
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return (h ? `${h}:${String(m).padStart(2, '0')}` : `${m}`) + `:${String(sec).padStart(2, '0')}`;
};
const fmtSpeed = (b) => (b ? (b > 1048576 ? `${(b / 1048576).toFixed(1)} MB/s` : `${Math.round(b / 1024)} KB/s`) : '');

/** "1:23", "01:02:03" o "45" → segundos. Vacío → null. Inválido → NaN. */
function parseTime(str) {
  str = (str || '').trim();
  if (!str) return null;
  const parts = str.split(':').map(Number);
  if (parts.some((n) => !isFinite(n) || n < 0) || parts.length > 3) return NaN;
  return parts.reduce((acc, n) => acc * 60 + n, 0);
}

function platformOf(url) {
  try {
    const h = new URL(url).hostname.replace(/^www\.|^m\./, '');
    const map = [['youtu', 'YouTube', '#ff0000'], ['tiktok', 'TikTok', '#00f2ea'], ['instagram', 'Instagram', '#e1306c'],
      ['facebook', 'Facebook', '#1877f2'], ['fb.watch', 'Facebook', '#1877f2'], ['x.com', 'X', '#f2f2f2'], ['twitter', 'X', '#f2f2f2'],
      ['vimeo', 'Vimeo', '#1ab7ea'], ['twitch', 'Twitch', '#9146ff'], ['soundcloud', 'SoundCloud', '#ff5500']];
    const hit = map.find(([k]) => h.includes(k));
    return hit ? { name: hit[1], color: hit[2] } : { name: h, color: '#a0a0a0' };
  } catch { return null; }
}

/** Playlist de verdad (no los "Mix" automáticos de YouTube, que son infinitos). */
function isPlaylist(url) {
  try {
    const u = new URL(url);
    const list = u.searchParams.get('list');
    if (list && !list.startsWith('RD')) return true;
    return /\/(playlist|channel|c|@)[^/]*/.test(u.pathname) && !u.searchParams.get('v');
  } catch { return false; }
}

// ── Ajustes (mismas claves que la 3.x) ───────────────────────────────────────
let settings = {};
let saveTimer;
function saveSettings() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => invoke('settings_save', { settings }), 400);
}

const RES_LABELS = { '': 'Máxima calidad', 2160: '4K', 1440: '2K', 1080: '1080p', 720: '720p', 480: '480p', 360: '360p' };

function applySettings(info) {
  settings.output_dir ||= info.downloadDir;
  // La 3.x guardaba "audio_only"; aquí "audio".
  settings.mode = settings.mode === 'audio_only' ? 'audio' : (settings.mode || 'video');
  $('#out-dir').value = settings.output_dir;
  $('#video-format').value = settings.video_format || 'MP4';
  $('#audio-format').value = settings.audio_format || 'MP3';
  $('#audio-bitrate').value = String(parseInt(settings.audio_bitrate) || 320);
  $('#resolution').value = settings.resolution_height ?? '1080';
  $('#cookies-browser').value = ['chrome', 'edge', 'firefox', 'brave', 'opera', 'vivaldi'].includes(settings.cookies_browser) ? settings.cookies_browser : '';
  $('#cookies-file').textContent = settings.cookies_file || '';
  setMode(settings.mode);
}

function readOptions() {
  settings.video_format = $('#video-format').value;
  settings.audio_format = $('#audio-format').value;
  settings.audio_bitrate = `${$('#audio-bitrate').value} kbps`;
  settings.resolution_height = $('#resolution').value;
  settings.cookies_browser = $('#cookies-browser').value || 'ninguno';
  $('#mode-video-detail').textContent = `${settings.video_format} · ${RES_LABELS[settings.resolution_height] || 'Máx.'}`;
  $('#mode-audio-detail').textContent = `${settings.audio_format} · ${$('#audio-bitrate').value}k`;
  saveSettings();
}

function setMode(mode) {
  settings.mode = mode;
  $$('.mode').forEach((b) => b.classList.toggle('on', b.dataset.mode === mode));
  const video = mode === 'video';
  $('#opt-res').hidden = !video;
  $('#opt-vfmt').hidden = !video;
  $('#opt-afmt').hidden = video;
  $('#opt-abr').hidden = video || ['WAV', 'FLAC'].includes($('#audio-format').value);
  readOptions();
}

// ── Navegación ───────────────────────────────────────────────────────────────
function showPage(page) {
  $$('#nav button').forEach((b) => b.classList.toggle('active', b.dataset.page === page));
  $$('main > section').forEach((s) => (s.hidden = s.dataset.page !== page));
  if (page === 'history') renderHistory();
  window.dispatchEvent(new CustomEvent('mxp:page', { detail: page }));
}

// ── Vista previa ─────────────────────────────────────────────────────────────
let previewToken = 0;
async function updatePreview() {
  const url = $('#url').value.trim();
  $('#url-clear').hidden = !url;
  const p = platformOf(url);
  const badge = $('#platform');
  badge.hidden = !p;
  if (p) { badge.textContent = p.name; badge.style.color = p.color; }

  const token = ++previewToken;
  const thumb = $('#thumb'), meta = $('#meta');
  if (!p) {
    thumb.style.backgroundImage = ''; thumb.textContent = 'Sin vista previa';
    meta.innerHTML = `<div class="details">${url ? 'Eso no parece un enlace.' : 'Pega un enlace para ver qué vas a descargar.'}</div>`;
    return;
  }
  if (isPlaylist(url)) {
    thumb.style.backgroundImage = ''; thumb.textContent = 'Lista';
    meta.innerHTML = '<div class="title">Lista de reproducción o canal</div><div class="details">Al descargar se añadirán todos sus videos a la cola.</div>';
    return;
  }
  thumb.style.backgroundImage = ''; thumb.textContent = 'Cargando…';
  meta.innerHTML = '<div class="details">Buscando el video…</div>';
  try {
    const info = await invoke('video_info', cookieArgs({ url }));
    if (token !== previewToken) return; // llegó tarde: el usuario ya pegó otra cosa
    thumb.textContent = '';
    thumb.style.backgroundImage = info.thumbnail ? `url("${encodeURI(info.thumbnail)}")` : '';
    meta.innerHTML = `<div class="title">${esc(info.title || 'Sin título')}</div>
      <div class="details">${esc([info.uploader, fmtTime(info.duration), info.extractor_key].filter(Boolean).join(' · '))}</div>`;
  } catch (e) {
    if (token !== previewToken) return;
    thumb.textContent = 'Error';
    meta.innerHTML = `<div class="error">${esc(e.message)}<small>${esc(e.hint)}</small></div>`;
  }
}

function cookieArgs(extra = {}) {
  return { ...extra, cookiesBrowser: $('#cookies-browser').value || null, cookiesFile: settings.cookies_file || null };
}

// ── Cola ─────────────────────────────────────────────────────────────────────
const MAX_PARALLEL = 3;
const queue = []; // { key, url, request, state, percent, title, speed, eta, jobId, file, error }
let nextKey = 1;

function buildRequest(url) {
  const mode = settings.mode;
  const start = parseTime($('#trim-start').value), end = parseTime($('#trim-end').value);
  if (Number.isNaN(start) || Number.isNaN(end)) throw new Error('El recorte no es válido. Usa el formato mm:ss, por ejemplo 1:30.');
  if (start != null && end != null && end <= start) throw new Error('El final del recorte tiene que ir después del inicio.');
  const audio = mode !== 'video';
  return {
    url,
    kind: audio ? 'audio' : 'video',
    max_height: audio ? null : (Number($('#resolution').value) || null),
    format: audio ? (mode === 'text' ? 'mp3' : $('#audio-format').value.toLowerCase()) : $('#video-format').value.toLowerCase(),
    audio_bitrate: Number($('#audio-bitrate').value) || 320,
    output_dir: settings.output_dir,
    start, end,
    cookies_browser: $('#cookies-browser').value || null,
    cookies_file: settings.cookies_file || null,
  };
}

function enqueue(urls) {
  let request;
  try { request = buildRequest(''); } catch (e) { toast(e.message); return; }
  for (const url of urls) {
    queue.push({ key: nextKey++, url, request: { ...request, url }, transcribe: settings.mode === 'text', state: 'waiting', percent: 0, title: url });
  }
  renderQueue();
  pump();
}

async function pump() {
  while (queue.filter((j) => j.state === 'running').length < MAX_PARALLEL) {
    const job = queue.find((j) => j.state === 'waiting');
    if (!job) break;
    job.state = 'running';
    job.status = 'fetching';
    try {
      job.jobId = await invoke('download_start', { request: job.request });
    } catch (e) {
      job.state = 'failed';
      job.error = { message: String(e), hint: '' };
    }
    renderQueue();
  }
}

T.event.listen('download', ({ payload: p }) => {
  const job = queue.find((j) => j.jobId === p.id);
  if (!job) return;
  job.status = p.status;
  job.percent = p.percent ?? job.percent;
  job.speed = p.speed; job.eta = p.eta;
  if (p.title) job.title = p.title;
  if (p.file) job.file = p.file;
  if (p.status === 'finished') {
    job.state = 'done';
  } else if (p.status === 'error') { job.state = 'failed'; job.error = p.error; }
  else if (p.status === 'cancelled') { job.state = 'cancelled'; }
  if (job.state !== 'running') pump();
  renderQueue();
});

const STATUS_TEXT = { fetching: 'Preparando…', downloading: 'Descargando', processing: 'Procesando…' };

function renderQueue() {
  const list = $('#queue');
  $('#queue-empty').hidden = queue.length > 0;
  $$('.job', list).forEach((el) => el.remove());
  for (const j of queue) {
    const el = document.createElement('div');
    el.className = `job ${j.state === 'done' ? 'done' : ''} ${j.state === 'failed' ? 'failed' : ''}`;
    let status;
    if (j.state === 'waiting') status = '<span>En espera</span>';
    else if (j.kind === 'transcribe' && j.state === 'running') status = `<span>${esc(j.message || 'Transcribiendo…')} ${Math.round(j.percent || 0)} %</span>`;
    else if (j.state === 'running') status = `<span>${STATUS_TEXT[j.status] || 'Descargando'} ${j.status === 'downloading' ? Math.round(j.percent) + ' %' : ''}</span><span>${esc(fmtSpeed(j.speed))}</span>`;
    else if (j.state === 'done') status = '<span>Listo</span>';
    else if (j.state === 'cancelled') status = '<span>Cancelado</span>';
    else status = '';
    el.innerHTML = `<div class="t" title="${esc(j.title)}">${esc(j.title)}</div>
      ${j.state === 'failed'
        ? `<div class="s err">${esc(j.error?.message)} ${esc(j.error?.hint)}</div>`
        : `<div class="s">${status}</div>`}
      <div class="bar"><i style="width:${j.state === 'done' ? 100 : j.percent || 0}%"></i></div>
      <div class="acts"></div>`;
    const acts = $('.acts', el);
    const btn = (label, fn) => { const b = document.createElement('button'); b.textContent = label; b.onclick = fn; acts.append(b); };
    if (j.kind === 'transcribe') {
      if (j.state === 'running') btn('Cancelar', () => invoke('transcribe_cancel', { id: j.jobId }));
      if (j.state === 'done') btn('Ver texto', () => j.onView());
      if (j.state === 'failed') btn('Reintentar', () => j.onRetry());
      if (!acts.children.length) acts.remove();
      list.append(el);
      continue;
    }
    if (j.state === 'running') btn('Cancelar', () => invoke('download_cancel', { id: j.jobId }));
    if (j.state === 'waiting') btn('Quitar', () => { queue.splice(queue.indexOf(j), 1); renderQueue(); });
    if (j.state === 'done' && j.file) {
      btn('Abrir', () => T.opener.openPath(j.file).catch((e) => toast(String(e))));
      btn('Carpeta', () => T.opener.revealItemInDir(j.file).catch((e) => toast(String(e))));
    }
    if (j.state === 'failed' || j.state === 'cancelled') btn('Reintentar', () => { j.state = 'waiting'; j.percent = 0; j.error = null; renderQueue(); pump(); });
    if (!acts.children.length) acts.remove();
    list.append(el);
  }
}

async function startDownload(urls) {
  urls = urls.map((u) => u.trim()).filter(Boolean);
  if (!urls.length) { toast('Pega primero un enlace.'); return; }
  const bad = urls.find((u) => !platformOf(u));
  if (bad) { toast(`Esto no parece un enlace: ${bad}`); return; }
  // Modo Texto: la transcripción baja ella misma solo el audio.
  if (settings.mode === 'text') { urls.forEach((u) => window.MXP.transcribe(u)); return; }
  const expanded = [];
  for (const url of urls) {
    if (!isPlaylist(url)) { expanded.push(url); continue; }
    toast('Leyendo la lista…');
    try {
      const pl = await invoke('playlist_expand', cookieArgs({ url }));
      if (pl.urls.length > 1 && !confirm(`«${pl.title || 'Lista'}» tiene ${pl.urls.length} videos. ¿Añadirlos todos a la cola?`)) continue;
      expanded.push(...pl.urls);
    } catch (e) { toast(`${e.message} ${e.hint || ''}`, 6000); }
  }
  if (expanded.length) enqueue(expanded);
}

// ── Historial ────────────────────────────────────────────────────────────────
async function renderHistory() {
  const items = await invoke('history_list');
  const list = $('#history-list');
  if (!items.length) { list.innerHTML = '<div class="empty"><b>Aún no hay descargas</b>Lo que descargues aparecerá aquí.</div>'; return; }
  list.innerHTML = '';
  for (const h of items) {
    const el = document.createElement('div');
    el.className = 'item';
    el.innerHTML = `<span class="tag">${esc(h.format)}</span>
      <div class="grow"><div class="t">${esc(h.title)}</div><div class="d">${esc(h.date)}</div></div>`;
    const b = (label, fn) => { const x = document.createElement('button'); x.className = 'btn'; x.textContent = label; x.onclick = fn; el.append(x); };
    if (h.file) b('Abrir', () => T.opener.openPath(h.file).catch(() => toast('El archivo ya no está en su sitio.')));
    b('Copiar enlace', () => navigator.clipboard.writeText(h.url).then(() => toast('Enlace copiado')));
    list.append(el);
  }
}

// ── Arranque ─────────────────────────────────────────────────────────────────
async function checkTools() {
  const tools = await invoke('tools_status');
  const broken = tools.filter((t) => !t.ok);
  const banner = $('#tools-banner');
  banner.hidden = !broken.length;
  banner.innerHTML = broken.length
    ? `<b>Faltan componentes:</b> ${broken.map((t) => `${esc(t.label)} (${esc(t.problem)})`).join('; ')}. Vuelve a ejecutar el instalador de MXP Suite para repararlo.`
    : '';
}

async function init() {
  $$('#nav button').forEach((b) => (b.onclick = () => showPage(b.dataset.page)));
  $$('.mode').forEach((b) => (b.onclick = () => setMode(b.dataset.mode)));
  ['#video-format', '#audio-format', '#audio-bitrate', '#resolution', '#cookies-browser'].forEach((s) => ($(s).onchange = () => setMode(settings.mode)));

  $$('.chip[data-panel]').forEach((chip) => (chip.onclick = () => {
    const panel = $(`.panel[data-panel="${chip.dataset.panel}"]`);
    panel.hidden = !panel.hidden;
    chip.classList.toggle('on', !panel.hidden);
  }));

  let debounce;
  $('#url').oninput = () => { clearTimeout(debounce); debounce = setTimeout(updatePreview, 500); };
  $('#url').onkeydown = (e) => { if (e.key === 'Enter') $('#go').click(); };
  $('#url-clear').onclick = () => { $('#url').value = ''; updatePreview(); $('#url').focus(); };
  $('#paste').onclick = async () => {
    try {
      $('#url').value = (await T.clipboardManager.readText()).trim();
      updatePreview();
    } catch { toast('El portapapeles está vacío o no tiene texto.'); }
  };
  $('#go').onclick = () => startDownload([$('#url').value]);

  $('#multi-toggle').onclick = () => {
    const multi = $('#multi-url').hidden;
    $('#multi-url').hidden = !multi;
    $('#single-url').hidden = multi;
    $('#multi-toggle').classList.toggle('on', multi);
  };
  $('#urls').oninput = () => { $('#multi-count').textContent = `${$('#urls').value.split('\n').filter((l) => l.trim()).length} enlaces`; };
  $('#go-multi').onclick = () => startDownload($('#urls').value.split('\n'));

  $('#out-dir-btn').onclick = async () => {
    const dir = await T.dialog.open({ directory: true, defaultPath: settings.output_dir });
    if (dir) { settings.output_dir = dir; $('#out-dir').value = dir; saveSettings(); }
  };
  $('#open-folder').onclick = () => T.opener.openPath(settings.output_dir).catch((e) => toast(String(e)));
  $('#cookies-file-btn').onclick = async () => {
    const f = await T.dialog.open({ filters: [{ name: 'cookies.txt', extensions: ['txt'] }] });
    settings.cookies_file = f || '';
    $('#cookies-file').textContent = settings.cookies_file;
    saveSettings();
  };
  $('#queue-clear').onclick = () => {
    for (let i = queue.length - 1; i >= 0; i--) if (!['running', 'waiting'].includes(queue[i].state)) queue.splice(i, 1);
    renderQueue();
  };
  $('#history-clear').onclick = async () => { if (confirm('¿Borrar todo el historial?')) { await invoke('history_clear'); renderHistory(); } };

  const [info, saved] = await Promise.all([invoke('app_info'), invoke('settings_load')]);
  $('#version').textContent = `v${info.version}`;
  settings = saved;
  applySettings(info);
  showPage('download');
  checkTools();
}

// Lo que comparten las demás páginas (transcribe.js, tools.js).
window.MXP = { invoke, esc, toast, queue, renderQueue, showPage, fmtTime, get settings() { return settings; }, saveSettings, cookieArgs };

init().catch((e) => toast(`Error al iniciar la interfaz: ${e}`, 10000));
