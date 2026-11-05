# V0.2.2 Command Manifest

## Build
- `npm run build:data-provider` (products/librechat-custom)
- `npm run build:api` (products/librechat-custom)
- `npm run build:client` → `cd client && npm run build`

## Test
- `npx jest --config jest.config.cjs --runInBand --forceExit src/components/Life/__tests__/ReminderCards.spec.tsx` (client)
- `py -m pytest services/life-core/tests -q` (requires project venv)
- `node --test tests/gateway.test.mjs` (root)

## Static Checks
- `npx prettier --check <files>`
- `npm run sort-imports:check -- --files <files>`
- `npx eslint <files>`

## Service Restart
- `docker restart lifecompanion-librechat` (after client build)
- `.\services\life-core\run.ps1` (after Python changes)
- `.\apps\product-portal\run.ps1 -Port 3001` (after gateway changes)

## Zhipu Configuration
- `py scripts/configure-zhipu.py` (validates key before writing)
- Manual edit: `infra/runtime/zhipu-api.local.txt`
