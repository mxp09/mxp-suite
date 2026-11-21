// Escenario: pegar enlace, ver vista previa, descargar como video, esperar a la cola.
const $ = (s) => document.querySelector(s);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = [];
document.querySelector('.mode[data-mode="video"]').click();
$('#resolution').value = '360'; $('#resolution').dispatchEvent(new Event('change'));
$('#url').value = 'https://www.youtube.com/watch?v=jNQXAC9IVRw';
$('#url').dispatchEvent(new Event('input'));
for (let i = 0; i < 60 && !$('#meta .title'); i++) await sleep(500);
log.push('preview: ' + ($('#meta .title')?.textContent || $('#meta').textContent));
log.push('platform: ' + $('#platform').textContent);
$('#go').click();
for (let i = 0; i < 240; i++) {
  await sleep(500);
  const job = $('.job');
  if (job && /Listo|Error|err/.test(job.className + job.textContent) && !/Descargando|Preparando|Procesando/.test(job.textContent)) break;
}
const job = $('.job');
log.push('cola: ' + job.textContent.replace(/\s+/g, ' ').trim());
log.push('botones: ' + [...job.querySelectorAll('button')].map((b) => b.textContent).join(','));
return log.join('\n');
