import { createGateway } from "../../apps/product-portal/server.mjs";

const port = Number(process.env.PORT || 4182);
const chatTarget = process.env.CHAT_TARGET || "http://127.0.0.1:3092";
const lifeTarget = process.env.LIFE_TARGET || "http://127.0.0.1:8032";

createGateway({ chatTarget, lifeTarget }).listen(port, "127.0.0.1", () => {
  process.stdout.write(`B2 gateway listening on http://127.0.0.1:${port}\n`);
});
