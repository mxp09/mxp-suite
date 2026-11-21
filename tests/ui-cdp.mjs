// Maneja la interfaz real de MXP Suite por el protocolo de depuración de WebView2.
// Uso: arrancar la app con WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9222
//      y luego: node tests/ui-cdp.mjs <archivo.js con el escenario>
import { readFileSync } from 'node:fs';

const targets = await (await fetch('http://127.0.0.1:9222/json')).json();
const page = targets.find((t) => t.type === 'page');
if (!page) throw new Error('No hay página de WebView2 en el puerto 9222');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r, { once: true }));
let id = 0;
const pending = new Map();
ws.addEventListener('message', (m) => {
  const msg = JSON.parse(m.data);
  if (pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
});
const send = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
export async function evaluate(expr) {
  const res = await send('Runtime.evaluate', { expression: `(async()=>{${expr}})()`, awaitPromise: true, returnByValue: true });
  if (res.result?.exceptionDetails) throw new Error(JSON.stringify(res.result.exceptionDetails));
  return res.result?.result?.value;
}
// `--shot archivo.png`: captura SOLO el contenido de la app (no la pantalla del usuario).
const shot = process.argv.indexOf('--shot');
if (shot > 0) {
  const { writeFileSync } = await import('node:fs');
  const r = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(process.argv[shot + 1], Buffer.from(r.result.data, 'base64'));
  console.log('captura:', process.argv[shot + 1]);
  ws.close();
  process.exit(0);
}
const scenario = readFileSync(process.argv[2], 'utf8');
const out = await evaluate(scenario);
console.log(typeof out === 'string' ? out : JSON.stringify(out, null, 2));
ws.close();
