# V0.2.2 Failure Log

| ID | Category | Detail | Severity |
|----|----------|--------|----------|
| DATA-1 | Original data preservation | memory_permissions row changed recall_consent, sensitive_consent, updated_at without attributed logged operation | medium |
| PERF-1 | Lighthouse | Default port 3080 conflicted with running service; isolated 3098 failed on Chinese UI expecting English Sign up | high |
| ZH-WEB-1 | Admin UI | Web configuration interface and hide switch not implemented; only local text file entry exists | low |
| DEV-1 | Device delivery | Push notification to mobile/OS cannot be confirmed; ntfy accept + in-app read != device delivered | medium |
| LLM-1 | Model output quality | GLM-4.7 occasionally outputs incorrect dates (e.g. "5月20日" for Nov 2026) in free-form text; does not affect structured reminder data | low |
