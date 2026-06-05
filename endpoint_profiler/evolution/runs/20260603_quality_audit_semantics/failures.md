# Remaining Failures

Current MA profile output fails the Source Sampling Audit.

Representative sampled gaps:

- `SolutionHubAutoConfiguration.java`: expected `DATAMODEL`, found none.
- `MarketingTargetClient.java`: expected `HTTP_CALL`, found none.
- `SMSSignatureSyncerClient.java`: expected `HTTP_CALL`, found none.
- `AuditLogConfig.java`: expected `MESSAGE_PRODUCER`, found none.
- `CanvasNotifyController.java`: expected `EVENT_BUS_PUBLISHER` and `HTTP_API`, found only `HTTP_API`.

Next patch targets:

- Improve extraction for client wrappers and SDK interfaces that express remote calls without the currently recognized annotations.
- Improve message producer detection for configuration-driven producers.
- Review datamodel heuristics to separate true model endpoint evidence from utility/config class references.
- Re-run profiling and both quality audits after extraction-rule changes.
