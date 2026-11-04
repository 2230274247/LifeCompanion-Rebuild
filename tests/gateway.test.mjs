import { createServer } from "node:http";
import { test } from "node:test";
import assert from "node:assert/strict";
import { createGateway } from "../apps/product-portal/server.mjs";

test("gateway streams chat, preserves login and protects internal API", async () => {
  const seen = [];
  const backend = createServer((req, res) => {
    seen.push({ url: req.url, headers: req.headers });
    res.writeHead(200, { "Content-Type": "text/event-stream" });
    res.write("data: first\n\n");
    setTimeout(() => res.end("data: last\n\n"), 20);
  });
  await new Promise((resolve) => backend.listen(0, "127.0.0.1", resolve));
  const target = `http://127.0.0.1:${backend.address().port}`;
  const gateway = createGateway({ chatTarget: target, lifeTarget: target });
  await new Promise((resolve) => gateway.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${gateway.address().port}`;
  try {
    const chat = await fetch(`${base}/api/ask`, { headers: { Cookie: "refreshToken=private" } });
    assert.equal(chat.headers.get("content-type"), "text/event-stream");
    assert.equal(await chat.text(), "data: first\n\ndata: last\n\n");
    assert.equal(seen[0].headers.cookie, "refreshToken=private");
    const life = await fetch(`${base}/life-api/api/v1/memories?page=2`, {
      headers: { Authorization: "Bearer access", Cookie: "refreshToken=private", "X-Internal-Token": "never" },
    });
    await life.text();
    assert.equal(seen[1].url, "/api/v1/memories?page=2");
    assert.equal(seen[1].headers.authorization, "Bearer access");
    assert.equal(seen[1].headers.cookie, undefined);
    assert.equal(seen[1].headers["x-internal-token"], undefined);
    assert.equal((await fetch(`${base}/life-api/internal/v1/events/ingest`)).status, 404);
    assert.equal((await fetch(`${base}/life-api/api/v1/memories`, { method: "POST" })).status, 404);
    assert.equal(seen.length, 2);
    const deepLink = await fetch(`${base}/memories/evt_012345678901234567890123`);
    assert.equal(deepLink.status, 200);
    await deepLink.text();
  } finally {
    await Promise.all([new Promise((resolve) => gateway.close(resolve)), new Promise((resolve) => backend.close(resolve))]);
  }
});

test("gateway allows reminder CRUD but never exposes the callback or execution hook", async () => {
  const backend = createServer((_req, res) => {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end("{}");
  });
  await new Promise((resolve) => backend.listen(0, "127.0.0.1", resolve));
  const gateway = createGateway({ lifeTarget: `http://127.0.0.1:${backend.address().port}` });
  await new Promise((resolve) => gateway.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${gateway.address().port}/life-api`;
  const reminderId = "rem_" + "a".repeat(32);
  try {
    const checks = [
      ["GET", "/api/v1/reminders"],
      ["POST", "/api/v1/reminders"],
      ["GET", `/api/v1/reminders/${reminderId}`],
      ["PATCH", `/api/v1/reminders/${reminderId}`],
      ["DELETE", `/api/v1/reminders/${reminderId}`],
      ["GET", "/api/v1/reminder-notifications"],
    ];
    await Promise.all(checks.map(async ([method, path]) => {
      const response = await fetch(base + path, { method });
      assert.equal(response.status, 200, method + " " + path);
      await response.text();
    }));
    for (const path of [
      "/api/v1/webhooks/vikunja",
      "/internal/v1/reminders/execute",
    ]) {
      assert.equal((await fetch(base + path, { method: "POST" })).status, 404);
    }
  } finally {
    await Promise.all([
      new Promise((resolve) => gateway.close(resolve)),
      new Promise((resolve) => backend.close(resolve)),
    ]);
  }
});

test("gateway exposes only the authenticated tool card methods, not internal tool hooks", async () => {
  const seen = [];
  const backend = createServer((req, res) => {
    seen.push(req.headers);
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end("{}");
  });
  await new Promise((resolve) => backend.listen(0, "127.0.0.1", resolve));
  const gateway = createGateway({ lifeTarget: `http://127.0.0.1:${backend.address().port}` });
  await new Promise((resolve) => gateway.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${gateway.address().port}/life-api`;
  const id = "tc_" + "a".repeat(28);
  try {
    for (const [method, path] of [
      ["GET", "/api/v1/tool-chats?conversation_id=owned"],
      ["POST", `/api/v1/tool-chats/${id}/select`],
      ["DELETE", `/api/v1/tool-chats/${id}`],
    ]) {
      const response = await fetch(base + path, { method, headers: {
        Authorization: "Bearer access", Cookie: "private", "X-Internal-Token": "never",
      } });
      assert.equal(response.status, 200, method + " " + path);
      await response.text();
    }
    for (const [method, path] of [
      ["POST", "/internal/v1/tools/chat"],
      ["POST", "/api/v1/tool-chats"],
      ["POST", "/api/v1/tool-chats/unbounded-id/select"],
      ["GET", `/api/v1/tool-chats/${id}/select`],
    ]) {
      assert.equal((await fetch(base + path, { method })).status, 404);
    }
    assert.equal(seen.length, 3);
    assert.ok(seen.every((headers) => headers.authorization === "Bearer access" &&
      headers.cookie === undefined && headers["x-internal-token"] === undefined));
  } finally {
    await Promise.all([
      new Promise((resolve) => gateway.close(resolve)),
      new Promise((resolve) => backend.close(resolve)),
    ]);
  }
});

test("gateway exposes only GET and POST for the fixed-account direct test route", async () => {
  const seen = [];
  const backend = createServer((req, res) => {
    seen.push({ method: req.method, url: req.url, headers: req.headers });
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end("{}");
  });
  await new Promise((resolve) => backend.listen(0, "127.0.0.1", resolve));
  const gateway = createGateway({
    lifeTarget: `http://127.0.0.1:${backend.address().port}`,
  });
  await new Promise((resolve) => gateway.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${gateway.address().port}/life-api`;
  try {
    for (const method of ["GET", "POST"]) {
      const response = await fetch(base + "/api/v1/test/direct-moment", {
        method,
        headers: {
          Authorization: "Bearer access",
          Cookie: "private",
          "X-Internal-Token": "never",
        },
      });
      assert.equal(response.status, 200, method);
      await response.text();
    }
    assert.equal(
      (await fetch(base + "/api/v1/test/direct-moment", { method: "PUT" })).status,
      404,
    );
    assert.equal(seen.length, 2);
    assert.ok(
      seen.every(
        (request) =>
          request.headers.authorization === "Bearer access" &&
          request.headers.cookie === undefined &&
          request.headers["x-internal-token"] === undefined,
      ),
    );
  } finally {
    await Promise.all([
      new Promise((resolve) => gateway.close(resolve)),
      new Promise((resolve) => backend.close(resolve)),
    ]);
  }
});
