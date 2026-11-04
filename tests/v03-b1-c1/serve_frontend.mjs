import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { createServer, request as httpRequest } from 'node:http';
import path from 'node:path';

const root = path.resolve(process.env.FRONTEND_ROOT);
const port = Number(process.env.FRONTEND_PORT || 4175);
const gateway = new URL(process.env.GATEWAY_TARGET || 'http://127.0.0.1:3002');
const contentTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webmanifest': 'application/manifest+json',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

function proxyLife(request, response) {
  const upstream = httpRequest(
    new URL(request.url, gateway),
    { method: request.method, headers: request.headers },
    (incoming) => {
      response.writeHead(incoming.statusCode || 502, incoming.headers);
      incoming.pipe(response);
      incoming.on('error', () => response.destroy());
    },
  );
  upstream.on('error', () => {
    if (!response.headersSent) {
      response.writeHead(502, { 'Content-Type': 'application/json' });
    }
    response.end(JSON.stringify({ error: 'GATEWAY_UNAVAILABLE' }));
  });
  request.pipe(upstream);
}

async function serveStatic(request, response) {
  const url = new URL(request.url || '/', 'http://localhost');
  let decoded;
  try {
    decoded = decodeURIComponent(url.pathname);
  } catch {
    response.writeHead(400).end('Bad request');
    return;
  }
  let target = path.resolve(root, `.${decoded}`);
  if (target !== root && !target.startsWith(root + path.sep)) {
    response.writeHead(403).end('Forbidden');
    return;
  }
  try {
    const info = await stat(target);
    if (info.isDirectory()) {
      target = path.join(target, 'index.html');
    }
  } catch {
    if (path.extname(decoded)) {
      response.writeHead(404).end('Not found');
      return;
    }
    target = path.join(root, 'index.html');
  }
  const extension = path.extname(target).toLowerCase();
  response.writeHead(200, {
    'Content-Type': contentTypes[extension] || 'application/octet-stream',
    'Cache-Control': extension === '.html' ? 'no-store' : 'public, max-age=31536000, immutable',
    'X-Content-Type-Options': 'nosniff',
  });
  if (request.method === 'HEAD') {
    response.end();
    return;
  }
  createReadStream(target).on('error', () => response.destroy()).pipe(response);
}

createServer((request, response) => {
  if ((request.url || '').startsWith('/life-api/')) {
    proxyLife(request, response);
    return;
  }
  void serveStatic(request, response);
}).listen(port, '127.0.0.1', () => {
  process.stdout.write(`frontend ${port} -> gateway ${gateway.origin}\n`);
});
