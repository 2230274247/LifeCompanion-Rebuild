const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const distRoot =
  process.env.BEFORE_DIST ||
  path.resolve(
    'H:/LifeCompanion-Rebuild-G1-Backups/20261104_230901/worktree/p00-p07-20261103/products/librechat-custom/client/dist',
  );
const port = Number(process.env.BEFORE_PORT || 3091);
const gateway = {
  hostname: '127.0.0.1',
  port: Number(process.env.BEFORE_GATEWAY_PORT || 3037),
};

const contentTypes = {
  '.br': 'application/octet-stream',
  '.css': 'text/css; charset=utf-8',
  '.gif': 'image/gif',
  '.gz': 'application/octet-stream',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ttf': 'font/ttf',
  '.webmanifest': 'application/manifest+json',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

function proxy(request, response) {
  const upstream = http.request(
    {
      ...gateway,
      method: request.method,
      path: request.url,
      headers: {
        ...request.headers,
        host: `${gateway.hostname}:${gateway.port}`,
      },
    },
    (upstreamResponse) => {
      response.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers);
      upstreamResponse.pipe(response);
    },
  );
  upstream.on('error', (error) => {
    response.writeHead(502, { 'content-type': 'text/plain; charset=utf-8' });
    response.end(`Backup UI API proxy failed: ${error.message}`);
  });
  request.pipe(upstream);
}

function serveFile(response, filePath) {
  const stat = fs.statSync(filePath);
  response.writeHead(200, {
    'content-type':
      contentTypes[path.extname(filePath).toLowerCase()] ?? 'application/octet-stream',
    'content-length': stat.size,
    'cache-control': filePath.endsWith('index.html') ? 'no-store' : 'public, max-age=60',
  });
  fs.createReadStream(filePath).pipe(response);
}

const server = http.createServer((request, response) => {
  const url = new URL(request.url || '/', `http://127.0.0.1:${port}`);
  if (
    url.pathname.startsWith('/api') ||
    url.pathname.startsWith('/life-api') ||
    url.pathname.startsWith('/oauth')
  ) {
    proxy(request, response);
    return;
  }

  const requestedPath = path.resolve(distRoot, `.${decodeURIComponent(url.pathname)}`);
  const insideDist =
    requestedPath === distRoot || requestedPath.startsWith(`${distRoot}${path.sep}`);
  if (insideDist && fs.existsSync(requestedPath) && fs.statSync(requestedPath).isFile()) {
    serveFile(response, requestedPath);
    return;
  }

  const acceptsHtml = request.headers.accept?.includes('text/html');
  if (acceptsHtml || !path.extname(url.pathname)) {
    serveFile(response, path.join(distRoot, 'index.html'));
    return;
  }

  response.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
  response.end('Not found');
});

server.listen(port, '127.0.0.1', () => {
  console.log(`BACKUP_UI_${port}_READY`);
});
