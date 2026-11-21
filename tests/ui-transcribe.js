window.MXP_TEST_FILE = "C:/Users/mapac/AppData/Local/Temp/claude/a8e94c3e3dfbc274/8598ef86-cedc-4331-b3da-f1e48adc7585/scratchpad/entrevista ñandú.webm";
// Escenario: transcribir un archivo local desde la página Transcribir y abrir el resultado.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (s) => document.querySelector(s);
document.querySelector('#nav button[data-page="transcribe"]').click();
for (let i = 0; i < 20 && !$('#tr-model option[value]:not([value=""])'); i++) await sleep(300);
$('#tr-source').value = window.MXP_TEST_FILE;
$('#tr-go').click();
for (let i = 0; i < 600; i++) {
  await sleep(500);
  const j = window.MXP.queue.find((x) => x.kind === 'transcribe');
  if (j && ['done', 'failed'].includes(j.state)) break;
}
const job = window.MXP.queue.find((x) => x.kind === 'transcribe');
if (job.state === 'done') job.onView();
await sleep(500);
return [`estado: ${job.state} ${job.error?.message || ''}`, `modelo: ${$('#tr-model').value}`, `meta: ${$('#tr-meta').textContent}`,
  `frases: ${[...document.querySelectorAll('#tr-editor [data-i]')].map((e) => e.textContent).join(' | ')}`].join('\n');
