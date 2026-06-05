# Version: v20260604_datamodel_dataapi_split

## Summary

Endpoint Profiler now supports access-specific DataAPI endpoint kinds:
`DATA_API_CALL` and `DATA_API_STREAM`. Their identifiers remain datamodel FQNs.
Plain `DATAMODEL` remains available for semantic model evidence without a
visible concrete data-proxy access mode.

## Validation

CDP profiling and quality audits pass. The CDP run shows that explicit DataAPI
access can be split, but not all datamodel evidence can safely collapse into the
two new kinds.

## Residual Risk

Some DataAPI calls pass dynamic FQN variables such as values returned from model
metadata or open tag configuration. These should not be emitted as resolved
`DATA_API_*` endpoints until the FQN can be traced to a concrete model.

