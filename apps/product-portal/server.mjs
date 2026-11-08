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
    const collabId = "[a-z]{2,8}_[a-f0-9]{32}";
    const publicLifeRoute =
      (request.method === "GET" && path === "/health") ||
      (request.method === "GET" && /^\/api\/v1\/(?:me|memory-status|chat-links|memories(?:\/evt_[a-f0-9]{24})?|knowledge(?:\/(?:recall|mem_[a-f0-9]{24}))?)$/.test(path)) ||
      (request.method === "PATCH" && path === "/api/v1/me/settings") ||
      (["GET", "PUT"].includes(request.method) && path === "/api/v1/moment-settings") ||
      (request.method === "GET" && path === "/api/v1/moments") ||
      (["GET", "DELETE"].includes(request.method) && /^\/api\/v1\/moments\/mom_[a-f0-9]{24}$/.test(path)) ||
      (request.method === "POST" && /^\/api\/v1\/moments\/mom_[a-f0-9]{24}\/(?:retry|publish)$/.test(path)) ||
      (request.method === "POST" && /^\/api\/v1\/knowledge\/mem_[a-f0-9]{24}\/exclude-moments$/.test(path)) ||
      (["GET", "POST"].includes(request.method) && path === "/api/v1/test/direct-moment") ||
      (["GET", "POST"].includes(request.method) && path === "/api/v1/reminders") ||
      (request.method === "POST" && path === "/api/v1/reminder-provisioning") ||
      (["GET", "POST"].includes(request.method) && path === "/api/v1/reminder-drafts") ||
      (["PATCH", "DELETE"].includes(request.method) && /^\/api\/v1\/reminder-drafts\/rd_[a-f0-9]{32}$/.test(path)) ||
      (request.method === "POST" && /^\/api\/v1\/reminder-drafts\/rd_[a-f0-9]{32}\/(?:confirm|reconcile|select)$/.test(path)) ||
      (["GET", "PATCH", "DELETE"].includes(request.method) && /^\/api\/v1\/reminders\/rem_[a-f0-9]{32}$/.test(path)) ||
      (request.method === "GET" && path === "/api/v1/reminder-notifications") ||
      (["PATCH", "DELETE"].includes(request.method) && /^\/api\/v1\/knowledge\/mem_[a-f0-9]{24}$/.test(path)) ||
      (["GET", "PATCH"].includes(request.method) && path === "/api/v1/collaboration/me") ||
      (request.method === "GET" && path === "/api/v1/users/search") ||
      (request.method === "GET" && path === "/api/v1/friends") ||
      (request.method === "POST" && path === "/api/v1/friends/requests") ||
      (request.method === "POST" && new RegExp(`^/api/v1/friends/requests/${collabId}/(?:accept|reject|cancel)$`).test(path)) ||
      (request.method === "DELETE" && new RegExp(`^/api/v1/friends/${collabId}$`).test(path)) ||
      (["POST", "DELETE"].includes(request.method) && new RegExp(`^/api/v1/blocks/${collabId}$`).test(path)) ||
      (["GET", "POST"].includes(request.method) && path === "/api/v1/spaces") ||
      (["GET", "DELETE"].includes(request.method) && new RegExp(`^/api/v1/spaces/${collabId}$`).test(path)) ||
      (request.method === "POST" && new RegExp(`^/api/v1/spaces/${collabId}/(?:invites|leave)$`).test(path)) ||
      (request.method === "POST" && new RegExp(`^/api/v1/space-invites/${collabId}/(?:accept|reject|cancel)$`).test(path)) ||
      (request.method === "PATCH" && new RegExp(`^/api/v1/spaces/${collabId}/owner$`).test(path)) ||
      (["GET", "POST"].includes(request.method) && new RegExp(`^/api/v1/spaces/${collabId}/messages$`).test(path)) ||
      (["PATCH", "DELETE"].includes(request.method) && new RegExp(`^/api/v1/spaces/${collabId}/messages/${collabId}$`).test(path)) ||
      (request.method === "POST" && new RegExp(`^/api/v1/spaces/${collabId}/messages/${collabId}/reactions$`).test(path)) ||
      (["GET", "POST"].includes(request.method) && new RegExp(`^/api/v1/direct-messages/${collabId}$`).test(path)) ||
      (request.method === "GET" && path === "/api/v1/collaboration/events") ||
      (["GET", "POST"].includes(request.method) && path === "/api/v1/grants") ||
      (request.method === "DELETE" && new RegExp(`^/api/v1/grants/${collabId}$`).test(path)) ||
      (["GET", "POST"].includes(request.method) && path === "/api/v1/grants/requests") ||
      (request.method === "POST" && new RegExp(`^/api/v1/grants/requests/${collabId}/(?:reject|cancel)$`).test(path)) ||
      (["GET", "POST"].includes(request.method) && path === "/api/v1/availability") ||
      (request.method === "DELETE" && new RegExp(`^/api/v1/availability/${collabId}$`).test(path)) ||
      (request.method === "GET" && new RegExp(`^/api/v1/shared-(?:availability|status)/${collabId}$`).test(path)) ||
      (request.method === "POST" && path === "/api/v1/shared-status") ||
      (request.method === "GET" && path === "/api/v1/shared-memories") ||
      (request.method === "GET" && path === "/api/v1/shared-memories/by-source") ||
      (request.method === "POST" && path === "/api/v1/shared-memories/invites") ||
      (request.method === "POST" && new RegExp(`^/api/v1/shared-memories/invites/${collabId}/(?:accept|reject|cancel)$`).test(path)) ||
      (request.method === "POST" && new RegExp(`^/api/v1/shared-memory-joins/${collabId}/(?:accept|reject)$`).test(path)) ||
      (request.method === "GET" && new RegExp(`^/api/v1/shared-memories/${collabId}$`).test(path)) ||
      (request.method === "POST" && new RegExp(`^/api/v1/shared-memories/${collabId}/(?:contributions|messages|invites|leave|agent/query)$`).test(path)) ||
      (request.method === "POST" && new RegExp(`^/api/v1/shared-memories/${collabId}/messages/${collabId}/reactions$`).test(path)) ||
      (request.method === "POST" && new RegExp(`^/api/v1/spaces/${collabId}/agent/query$`).test(path)) ||
      (request.method === "GET" && path === "/api/v1/notifications") ||
      (request.method === "PATCH" && new RegExp(`^/api/v1/notifications/${collabId}$`).test(path)) ||
      (request.method === "POST" && path === "/api/v1/care/forward-requests");
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
  const host = process.env.HOST || "127.0.0.1";
  const gateway = createGateway({
    chatTarget: process.env.LIFE_CHAT_TARGET || "http://127.0.0.1:3080",
    lifeTarget: process.env.LIFE_CORE_TARGET || "http://127.0.0.1:8010",
  });
  gateway.listen(port, host, () => {
    process.stdout.write(`Life Companion listening on http://${host}:${port}\n`);
  });
}
