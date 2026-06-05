# Contrast

Before this evolution:

- The skill text required source and graph trace audits.
- The executable verifier could pass even when the latest audit reports were older than `endpoints.json`.
- This created a silent bypass risk: endpoint extraction could be refreshed without refreshing traceability evidence.

After this evolution:

- The verifier fails stale or missing required audit reports.
- A complete run now needs current JSON/HTML plus current audit artifacts.
- The audit reports explicitly distinguish endpoint existence, source traceability, graph edge traceability, terminal endpoints, declared-only contracts, and cases requiring deeper caller expansion.

Remaining limitation:

- The smoke audit used one representative sample per present kind for this validation run. The skill-level audit rule still allows up to 10 diverse samples per kind and should be used for deeper QA runs.
- Graphify currently provides useful source/method nodes and some call edges, but not a complete endpoint-to-endpoint runtime chain graph for every sample.
