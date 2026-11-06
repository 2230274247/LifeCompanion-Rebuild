# P02 Dependency and License Matrix

Package identities and license expressions were read from the installed distribution metadata in the isolated P02 environment on 2026-11-03.

| Component | Version | Installed metadata / server license | Role | Runtime state |
|---|---|---|---|---|
| LangMem | 0.0.30 | MIT | Structured extraction and update proposal | Initial Zhipu baseline and 2026-11-04 DeepSeek extension passed |
| langchain-openai | 1.7.3 | MIT | Configured OpenAI-compatible transport | Used by LangMem call |
| Neo4j Python driver | 6.4.1 | Apache-2.0 AND Python-2.0 | Graph projection and structural recall | Authenticated Bolt/Cypher passed |
| Neo4j Community server | 5.26.32 | GPLv3 | Derived temporal graph | Isolated container healthy |
| graphiti-core | 0.31.2 | Apache-2.0 | Native temporal graph provider audit | Installed in P02 only; native API not connected |

Neo4j Community server use/distribution and Python driver licensing are distinct. Public redistribution and deployment still require the project's license gate. This is a runtime identity and metadata record, not a complete legal opinion or CVE audit.

No new embedding provider, account, key, or paid service was provisioned. No dependency was installed into the original canonical project's virtual environment.

The current application provider remains the existing DeepSeek endpoint/key.
The 2026-11-04 P03 dependency metadata additionally records LangGraph 1.2.19
and SQLite checkpoint 3.1.3; see `evidence/p03/dependency-metadata.json`.
