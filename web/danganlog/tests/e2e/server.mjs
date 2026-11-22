/* out/ を静的配信する最小サーバー (e2e 用)。 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = process.env.OUT_DIR ? path.resolve(process.env.OUT_DIR) : path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../out');
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.json': 'application/json', '.wasm': 'application/wasm', '.css': 'text/css', '.zip': 'application/zip', '.txt': 'text/plain', '.svg': 'image/svg+xml', '.ico': 'image/x-icon' };

export function startServer(port = 0) {
  const server = http.createServer((req, res) => {
    let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    if (p.endsWith('/')) p += 'index.html';
    const file = path.join(OUT, path.normalize(p));
    if (!file.startsWith(OUT)) { res.writeHead(403).end(); return; }
    fs.readFile(file, (err, data) => {
      if (err) { res.writeHead(404, { 'content-type': 'text/plain' }).end('not found'); return; }
      res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' });
      res.end(data);
    });
  });
  return new Promise((resolve) => server.listen(port, '127.0.0.1', () => resolve({ server, url: 'http://127.0.0.1:' + server.address().port })));
}
