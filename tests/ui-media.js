// Escenario: soltar un video y una imagen en Convertir (→ WEBM y WEBP), y el video en Comprimir (Discord).
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const DIR = 'C:/Users/mapac/AppData/Local/Temp/claude/a8e94c3e3dfbc274/8598ef86-cedc-4331-b3da-f1e48adc7585/scratchpad/';
const sec = (p) => document.querySelector(`section[data-page="${p}"]`);
document.querySelector('#nav button[data-page="convert"]').click();
window.dispatchEvent(new CustomEvent('mxp:drop', { detail: [DIR + 'vídeo de prueba.mov', DIR + 'foto ñ.png', DIR + 'nota.txt'] }));
await sleep(300);
sec('convert').querySelector('[data-target="video"]').value = 'webm';
sec('convert').querySelector('[data-target="image"]').value = 'webp';
sec('convert').querySelector('[data-go]').click();
document.querySelector('#nav button[data-page="compress"]').click();
window.dispatchEvent(new CustomEvent('mxp:drop', { detail: [DIR + 'vídeo de prueba.mov'] }));
await sleep(300);
sec('compress').querySelector('[data-size]').value = '10';
sec('compress').querySelector('[data-go]').click();
await sleep(500);
for (let i = 0; i < 240; i++) {
  await sleep(500);
  if (window.MXP.queue.filter((j) => j.kind === 'media').every((j) => j.state !== 'running')) break;
}
return window.MXP.queue.filter((j) => j.kind === 'media').map((j) => `${j.title} → ${j.state} ${j.file || j.error?.message || ''}`).join('\n');
