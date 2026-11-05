import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const root = path.resolve(import.meta.dirname, '..');
const promptPath = path.join(
  root,
  'docs/product/v0.2/prompts/life-companion-chat.v1.md',
);
const evalPath = path.join(root, 'docs/product/v0.2/chat-quality-evaluation.v1.json');
const configPath = path.join(root, 'products/librechat-custom/librechat.yaml');

const prompt = fs.readFileSync(promptPath, 'utf8');
const evaluation = JSON.parse(fs.readFileSync(evalPath, 'utf8'));
const config = fs.readFileSync(configPath, 'utf8');
const failures = [];

if (evaluation.samples.length !== 50) {
  failures.push(`expected 50 evaluation samples, received ${evaluation.samples.length}`);
}

const categories = new Set(evaluation.samples.map((sample) => sample.category));
for (const required of [
  'daily_share',
  'emotion',
  'explicit_creation',
  'task',
  'reminder',
  'memory_request',
  'correction',
  'privacy',
  'multi_turn',
  'safety',
  'boundary',
]) {
  if (!categories.has(required)) {
    failures.push(`missing evaluation category: ${required}`);
  }
}

const promptRequirements = [
  '普通对话，不是回忆生成任务',
  '通常 1–3 句',
  '最多提出一个轻量追问',
  '不得补写成真实经历',
  '不要用第一人称假扮用户',
  '用户明确要求创作时可以创作',
  '记忆抽取、回忆图和定时任务由独立后台完成',
  '除非后端已返回可验证的成功状态',
];
for (const phrase of promptRequirements) {
  if (!prompt.includes(phrase)) {
    failures.push(`prompt missing guardrail: ${phrase}`);
  }
}

if ((config.match(/promptPrefix: \|/g) ?? []).length !== 2) {
  failures.push('both life-companion model specs must declare promptPrefix');
}
if (!config.includes('版本：life-companion-chat.v1')) {
  failures.push('librechat.yaml promptPrefix does not declare the prompt version');
}
for (const phrase of ['普通对话，不是回忆生成任务', '不要用第一人称假扮用户', '独立后台完成']) {
  if (!config.includes(phrase)) {
    failures.push(`librechat.yaml promptPrefix missing guardrail: ${phrase}`);
  }
}

if (failures.length > 0) {
  console.error(failures.join('\n'));
  process.exit(1);
}

console.log(
  `PASS: ${evaluation.samples.length} samples across ${categories.size} categories; prompt and model specs match v1 guardrails.`,
);
