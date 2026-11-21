// Páginas Convertir y Comprimir: lista de archivos, opciones y cola.
'use strict';
(() => {
  const { invoke, esc, toast, queue, renderQueue } = window.MXP;
  const T = window.__TAURI__;

  const EXT = {
    video: ['mp4', 'mkv', 'mov', 'avi', 'webm', 'wmv', 'flv', 'm4v', 'mpg', 'mpeg', '3gp', 'ts', 'mts'],
    audio: ['mp3', 'wav', 'flac', 'm4a', 'aac', 'ogg', 'opus', 'wma', 'aiff', 'alac'],
    image: ['jpg', 'jpeg', 'png', 'webp', 'avif', 'bmp', 'tif', 'tiff', 'heic', 'heif', 'gif'],
  };
  const TARGETS = {
    video: [['mp4', 'MP4 (compatible con todo)'], ['mp4 (hevc)', 'MP4 HEVC (más ligero)'], ['mkv', 'MKV'], ['mov', 'MOV'], ['webm', 'WEBM'],
      ['webm (av1)', 'WEBM AV1 (el más ligero)'], ['gif', 'GIF animado'], ['mp3', 'Solo el audio: MP3'], ['wav', 'Solo el audio: WAV']],
    audio: [['mp3', 'MP3'], ['m4a', 'M4A'], ['wav', 'WAV'], ['flac', 'FLAC (sin pérdida)'], ['ogg', 'OGG (Opus)']],
    image: [['jpg', 'JPG'], ['png', 'PNG'], ['webp', 'WEBP'], ['avif', 'AVIF (el más ligero)'], ['bmp', 'BMP'], ['tiff', 'TIFF']],
  };
  const LABEL = { video: 'Videos', audio: 'Audios', image: 'Imágenes' };
  const typeOf = (p) => { const e = p.split('.').pop().toLowerCase(); return Object.keys(EXT).find((k) => EXT[k].includes(e)); };
  const name = (p) => p.split(/[\\/]/).pop();

  function page(rootId, mode) {
    const root = document.getElementById(rootId);
    root.classList.remove('panel');
    const files = [];
    let outDir = null;

    root.innerHTML = `
      <div class="drop" data-drop>
        <i class="i lg" style="--i:url(icons/upload.png)"></i>
        <b>Arrastra aquí tus archivos</b><span>Video, audio o imágenes (también fotos HEIC del iPhone)</span>
        <button class="btn" data-pick>Elegir archivos</button>
      </div>
      <div class="list" data-files style="margin-top:12px"></div>
      <div class="options" data-opts></div>
      <div class="row spread" style="margin-top:16px">
        <div class="row"><button class="chip" data-dest><i class="i sm" style="--i:url(icons/folder.png)"></i>Junto al original</button>
          <button class="link" data-clear>Vaciar lista</button></div>
        <button class="btn primary" data-go>${mode === 'convert' ? 'Convertir' : 'Comprimir'}</button>
      </div>`;
    const $ = (s) => root.querySelector(s);

    function renderOptions() {
      const types = [...new Set(files.map(typeOf))];
      let html = '';
      if (mode === 'convert') {
        for (const t of types) {
          html += `<label><span class="tiny-label">${LABEL[t]} a</span><select class="input" data-target="${t}">
            ${TARGETS[t].map(([v, l]) => `<option value="${v}">${l}</option>`).join('')}</select></label>`;
        }
        html += `<label><span class="tiny-label">Calidad</span><select class="input" data-level>
          <option value="none">Máxima</option><option value="medium">Buena (más ligero)</option></select></label>`;
      } else {
        html += `<label><span class="tiny-label">Compresión</span><select class="input" data-level>
          <option value="medium">Media (buena calidad)</option><option value="high">Alta (para redes)</option><option value="extreme">Extrema</option></select></label>`;
        if (types.includes('video')) {
          html += `<label><span class="tiny-label">Video: peso máximo</span><select class="input" data-size>
            <option value="">Sin límite (usa la compresión)</option><option value="16">WhatsApp (16 MB)</option>
            <option value="10">Discord (10 MB)</option><option value="25">Correo (25 MB)</option><option value="50">50 MB</option></select></label>`;
        }
      }
      $('[data-opts]').innerHTML = files.length ? html : '';
    }

    function render() {
      $('[data-files]').innerHTML = files.map((f, i) => `<div class="item"><span class="tag">${esc(f.split('.').pop().toUpperCase())}</span>
        <div class="grow"><div class="t">${esc(name(f))}</div></div><button class="btn" data-rm="${i}">Quitar</button></div>`).join('');
      renderOptions();
    }

    function add(paths) {
      let skipped = 0;
      for (const p of paths) {
        if (!typeOf(p)) skipped++;
        else if (!files.includes(p)) files.push(p);
      }
      if (skipped) toast(`${skipped} archivo(s) no son video, audio ni imagen y no se añadieron.`);
      render();
    }

    $('[data-pick]').onclick = async () => {
      const all = [...EXT.video, ...EXT.audio, ...EXT.image];
      const sel = await T.dialog.open({ multiple: true, filters: [{ name: 'Video, audio e imágenes', extensions: all }] });
      if (sel) add(Array.isArray(sel) ? sel : [sel]);
    };
    $('[data-files]').onclick = (e) => { const b = e.target.closest('[data-rm]'); if (b) { files.splice(+b.dataset.rm, 1); render(); } };
    $('[data-clear]').onclick = () => { files.length = 0; render(); };
    $('[data-dest]').onclick = async () => {
      const dir = await T.dialog.open({ directory: true });
      outDir = dir || null;
      $('[data-dest]').lastChild.textContent = outDir ? name(outDir) : 'Junto al original';
      $('[data-dest]').classList.toggle('on', !!outDir);
    };
    $('[data-go]').onclick = () => {
      if (!files.length) { toast('Añade primero algún archivo.'); return; }
      const level = $('[data-level]')?.value || 'none';
      const size = Number($('[data-size]')?.value) || null;
      for (const input of files.splice(0)) {
        const t = typeOf(input);
        const format = mode === 'convert' ? $(`[data-target="${t}"]`).value : '';
        const job = { input, format, level, target_mb: t === 'video' ? size : null, output_dir: outDir };
        const q = { kind: 'media', state: 'running', percent: 0, title: name(input), job };
        q.onRetry = () => start(q);
        queue.push(q);
        start(q);
      }
      render();
    };

    window.addEventListener('mxp:drop', (e) => {
      if (!document.querySelector(`section[data-page="${mode}"]`).hidden) add(e.detail);
    });
  }

  async function start(q) {
    q.state = 'running'; q.percent = 0; q.error = null;
    renderQueue();
    q.jobId = await invoke('media_start', { job: q.job });
  }

  T.event.listen('media', ({ payload: p }) => {
    const q = queue.find((j) => j.kind === 'media' && j.jobId === p.id);
    if (!q) return;
    q.percent = p.percent;
    if (p.status === 'done') { q.state = 'done'; q.file = p.file; window.MXP.notify('Listo', q.title); }
    if (p.status === 'error') { q.state = 'failed'; q.error = { message: p.error, hint: '' }; }
    if (p.status === 'cancelled') q.state = 'cancelled';
    renderQueue();
  });

  // Un solo receptor de arrastrar-y-soltar para toda la app: avisa a la página visible.
  T.webview.getCurrentWebview().onDragDropEvent(({ payload }) => {
    if (payload.type === 'drop' && payload.paths?.length) window.dispatchEvent(new CustomEvent('mxp:drop', { detail: payload.paths }));
  });

  page('convert-root', 'convert');
  page('compress-root', 'compress');
})();
