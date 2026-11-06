import { createServer, request as httpRequest } from "node:http";
import { pathToFileURL } from "node:url";

function sendJson(response, status, body) {
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  response.end(JSON.stringify(body));
}

export function createGateway({
  chatTarget = "http://127.0.0.1:3080",
  lifeTarget = "http://127.0.0.1:8010",
} = {}) {
  return createServer((request, response) => {
    const url = new URL(request.url || "/", "http://localhost");
    if (url.pathname === "/health") {
      sendJson(response, 200, { status: "ok", service: "life-companion-gateway" });
      return;
    }
    const isLife = url.pathname.startsWith("/life-api/");
    const path = isLife ? url.pathname.slice("/life-api".length) : url.pathname;
    // Explicit public methods only; internal hooks and service credentials stay server-side.
    const publicLifeRoute =
      (request.method === "GET" && /^\/api\/v1\/(?:me|chat-links|memories(?:\/evt_[a-f0-9]{24})?|knowledge(?:\/(?:recall|mem_[a-f0-9]{24}))?)$/.test(path)) ||
      (request.method === "PATCH" && path === "/api/v1/me/settings") ||
      (["GET", "PUT"].includes(request.method) && path === "/api/v1/moment-settings") ||
      (request.method === "GET" && path === "/api/v1/moments") ||
      (["GET", "DELETE"].includes(request.method) && /^\/api\/v1\/moments\/mom_[a-f0-9]{24}$/.test(path)) ||
      (request.method === "POST" && /^\/api\/v1\/moments\/mom_[a-f0-9]{24}\/retry$/.test(path)) ||
      (request.method === "POST" && /^\/api\/v1\/knowledge\/mem_[a-f0-9]{24}\/exclude-moments$/.test(path)) ||
      (request.method === "GET" && path === "/api/v1/tool-chats") ||
      (request.method === "POST" && /^\/api\/v1\/tool-chats\/tc_[a-f0-9]{28}\/select$/.test(path)) ||
      (request.method === "DELETE" && /^\/api\/v1\/tool-chats\/tc_[a-f0-9]{28}$/.test(path)) ||
      (["GET", "POST"].includes(request.method) && path === "/api/v1/reminders") ||
      (request.method === "POST" && path === "/api/v1/reminder-provisioning") ||
      (["GET", "POST"].includes(request.method) && path === "/api/v1/reminder-drafts") ||
      (["PATCH", "DELETE"].includes(request.method) && /^\/api\/v1\/reminder-drafts\/rd_[a-f0-9]{32}$/.test(path)) ||
      (request.method === "POST" && /^\/api\/v1\/reminder-drafts\/rd_[a-f0-9]{32}\/(?:confirm|reconcile|select)$/.test(path)) ||
      (["GET", "PATCH", "DELETE"].includes(request.method) && /^\/api\/v1\/reminders\/rem_[a-f0-9]{32}$/.test(path)) ||
      (request.method === "GET" && path === "/api/v1/reminder-notifications") ||
      (["PATCH", "DELETE"].includes(request.method) && /^\/api\/v1\/knowledge\/mem_[a-f0-9]{24}$/.test(path));
    if (isLife && (
      !publicLifeRoute
    )) {
      sendJson(response, 404, { error: "NOT_FOUND" });
      return;
    }
    const headers = { ...request.headers };
    delete headers.host;
    delete headers["x-internal-token"];
    if (isLife) delete headers.cookie;
    const upstream = httpRequest(new URL(path + url.search, isLife ? lifeTarget : chatTarget), {
      method: request.method,
      headers,
    }, (incoming) => {
      response.writeHead(incoming.statusCode || 502, incoming.headers);
      incoming.pipe(response);
      incoming.on("error", () => response.destroy());
    });
    // Stream bytes directly so model SSE is never buffered.
    upstream.setTimeout(isLife ? 30000 : 300000, () => upstream.destroy());
    upstream.on("error", () => {
      if (!response.headersSent) sendJson(response, 502, { error: "UPSTREAM_UNAVAILABLE" });
      else response.destroy();
    });
    response.on("close", () => upstream.destroy());
    request.on("aborted", () => upstream.destroy());
    request.pipe(upstream);
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const port = Number(process.env.PORT || 3001);
  createGateway().listen(port, "127.0.0.1", () => {
    process.stdout.write(`Life Companion listening on http://127.0.0.1:${port}\n`);
  });
}
