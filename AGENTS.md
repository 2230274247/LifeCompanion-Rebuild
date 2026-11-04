# Life Companion development rules

- Work only inside LifeCompanion-Rebuild; never modify Silver-economy.
- Preserve databases, secrets, upstream versions, and existing user changes.
- Reuse LibreChat chat components and Memos official APIs. Never expose service credentials.
- Follow `docs/DEVELOPMENT_LOG_POLICY.md` for every development task, including blocked tasks.
- Add an independent Chinese acceptance log and update its index after every task. Maintain architecture, product, and design indexes under `docs/` when their scope changes; never create future-dated completed logs.
- Independent upstream repositories retain their own contributor instructions. Archive local upstream diffs under `patches/` before delivery; never commit credentials or runtime data.
