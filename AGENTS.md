# Life Companion development rules

- Work only inside LifeCompanion-Rebuild; never modify Silver-economy.
- Preserve databases, secrets, upstream versions, and existing user changes.
- Reuse LibreChat chat components and Memos official APIs. Never expose service credentials.
- Follow `docs/DEVELOPMENT_LOG_POLICY.md` for every development task, including blocked tasks.
- Add an independent Chinese acceptance log and update its index after every task. Maintain architecture, product, and design indexes under `docs/` when their scope changes; never create future-dated completed logs.
- Independent upstream repositories retain their own contributor instructions. Archive local upstream diffs under `patches/` before delivery; never commit credentials or runtime data.

## Mandatory Git and Worktree gate

Before any development, test, cleanup, merge, or commit task, read and follow
`docs/development/GIT_WORKTREE_POLICY.md`. This rule applies to every future Codex task.

1. The only product baseline is `H:\AI For research institute\LifeCompanion-Rebuild`.
   Never use or recreate the deleted old project, and never replace a dirty worktree
   with a fresh clone.
2. Start with a fast, read-only audit: `git status --short --branch`,
   `git branch --show-current`, `git rev-parse HEAD`, `git worktree list --porcelain`,
   `git remote -v`, and `scripts/git/inspect-workspace.ps1`.
3. Use the repository root as the primary development worktree. Review every extra
   worktree before integration or removal; never delete or overwrite valuable work.
4. Create an automatic local Commit after each independently verified phase. Allow
   clearly labelled WIP checkpoints only when tests fail; never label WIP as complete.
5. Commit source, tests, migrations, design/task documents, safe templates, evidence
   reports, and license records. Never commit `.env`, credentials, private user data,
   raw databases, dependencies, caches, build output, or unmanaged runtime logs.
6. Use only the safe checkpoints in `scripts/git/`; provide explicit paths to
   `checkpoint.ps1`. Never default to `git add -A` or destructive git commands.
7. Local commits do not imply a remote push. With no validated remote, report
   `LOCAL_COMMITTED / PUSH_BLOCKED_NO_REMOTE`; never invent a remote.
8. Do not repeat full source snapshots because Git is dirty. Independently back up
   stateful databases, migrations, high-risk upgrades, or large directory moves.
9. Coordinate multiple agents by branch, task, and file ownership. Resolve conflicts
   explicitly; never choose one side blindly.
10. At task end report branch, HEAD, commit SHA, tests, remaining dirty files,
    worktree/remote state, push state, and the exact next continuation point.

Governance regression tests live in `tests/git-governance.ps1`.
