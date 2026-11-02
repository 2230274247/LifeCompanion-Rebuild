import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const port = Number(process.env.PORT || 3001);

const staticFiles = new Map([
  ["/", ["index.html", "text/html; charset=utf-8"]],
  ["/portal.css", ["portal.css", "text/css; charset=utf-8"]],
  ["/portal.js", ["portal.js", "text/javascript; charset=utf-8"]],
  ["/favicon.svg", ["favicon.svg", "image/svg+xml"]],
]);

const services = [
  { id: "librechat", name: "LibreChat", url: "http://127.0.0.1:3080/health" },
  { id: "memos", name: "Memos", url: "http://127.0.0.1:5230/healthz" },
  { id: "life-core", name: "life-core", url: "http://127.0.0.1:8010/health" },
];

async function serviceStatus(service) {
  try {
    const response = await fetch(service.url, {
      signal: AbortSignal.timeout(1800),
      headers: { Accept: "application/json" },
    });
    return { id: service.id, name: service.name, ok: response.ok };
  } catch {
    return { id: service.id, name: service.name, ok: false };
  }
}

function sendJson(response, status, body) {
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  response.end(JSON.stringify(body));
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://${request.headers.host || "localhost"}`);

  if (url.pathname === "/health") {
    sendJson(response, 200, { status: "ok", service: "product-portal" });
    return;
  }

  if (url.pathname === "/api/services/status") {
    const statuses = await Promise.all(services.map(serviceStatus));
    sendJson(response, 200, { checked_at: new Date().toISOString(), services: statuses });
    return;
  }

  const asset = staticFiles.get(url.pathname);
  if (!asset) {
    sendJson(response, 404, { error: "NOT_FOUND" });
    return;
  }

  try {
    const body = await readFile(join(root, asset[0]));
    response.writeHead(200, {
      "Content-Type": asset[1],
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    response.end(body);
  } catch {
    sendJson(response, 500, { error: "ASSET_READ_FAILED" });
  }
});

server.listen(port, "127.0.0.1", () => {
  process.stdout.write(`Life Companion portal listening on http://127.0.0.1:${port}\n`);
});
