# P02 Graphiti Native Status

Status: `BLOCKED_EMBEDDING`.

- `graphiti-core==0.31.2` is installed only in the ignored P02 isolation environment and recorded in `requirements-p02.txt`.
- `GraphitiProvider` reports a fail-closed status and rejects native search or episode writes unless an embedding provider is configured and the adapter is explicitly validated.
- No embedding provider or embedding key was configured or called. No vector was fabricated.
- Neo4j structural memory projection and keyword/relationship retrieval operate independently of Graphiti.
- The installed package's API is not yet connected to Life-core and no Graphiti episode was written. Do not report native Graphiti as integrated or passed.

To unblock: approve and configure a compatible embedding provider under the existing cost and privacy policy, then validate its API/terms and implement the provider adapter. No new provider or charge was created for this stage.
