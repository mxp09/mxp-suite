// Escenario: 30 trabajos terminados en la cola → se puede desplazar y quitar uno concreto.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const q = window.MXP.queue;
for (let i = 1; i <= 30; i++) q.push({ kind: 'download', state: i % 7 ? 'done' : 'failed', title: `Video ${i}`, percent: 100, file: null, error: { message: 'Error de prueba', hint: '' } });
window.MXP.renderQueue();
await sleep(200);
const list = document.querySelector('#queue');
const scrollable = list.scrollHeight > list.clientHeight;
list.scrollTop = list.scrollHeight;
await sleep(200);
const scrolled = list.scrollTop > 0;
const target = [...list.querySelectorAll('.job')].find((j) => j.querySelector('.t').textContent === 'Video 15');
target.querySelector('.x').click();
await sleep(200);
const titles = [...list.querySelectorAll('.job .t')].map((t) => t.textContent);
list.scrollTop = 0;
return `desplazable: ${scrollable} (alto ${list.clientHeight}px, contenido ${list.scrollHeight}px)\nse desplazó: ${scrolled}\nquedan: ${titles.length} · sigue "Video 15": ${titles.includes('Video 15')} · sigue "Video 16": ${titles.includes('Video 16')}`;
