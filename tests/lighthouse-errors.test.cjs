const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const root = path.resolve(__dirname, '..');
const ts = require(path.join(root, 'products/librechat-custom/node_modules/typescript'));
const filename = path.join(root, 'products/librechat-custom/e2e/lighthouse/audit.ts');
const compiled = new Module(filename, module);
compiled.filename = filename;
compiled.paths = Module._nodeModulePaths(path.dirname(filename));
compiled._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, filename);
const { lighthouseFailure } = compiled.exports;

test('child-process command, stderr, Cookie and token cannot reach performance logs', () => {
  const error = Object.assign(new Error('Command failed: --extra-headers=TEST_SECRET_SENTINEL'), {
    code: 1, stderr: 'Cookie: TEST_SECRET_SENTINEL', stdout: 'TEST_SECRET_SENTINEL',
  });
  const safe = lighthouseFailure(error);
  assert.equal(safe.message, 'LIGHTHOUSE_PROCESS_FAILED (exit 1)');
  assert.ok(!safe.stack.includes('TEST_SECRET_SENTINEL'));
  assert.equal(safe.cause, undefined);
});

test('unexpected thrown values and nonnumeric codes are never disclosed', () => {
  for (const value of ['TEST_SECRET_SENTINEL', { code: 'TEST_SECRET_SENTINEL' }, null]) {
    assert.equal(lighthouseFailure(value).message, 'LIGHTHOUSE_PROCESS_FAILED (exit unknown)');
  }
});
