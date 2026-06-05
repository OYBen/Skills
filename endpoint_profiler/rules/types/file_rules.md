# FILE Rules

## Purpose

`FILE` is an egress endpoint for system integration through shared files,
object storage objects, SFTP drops, batch exchange files, or partner feed
paths.

## Evidence

- OSS/S3/object storage operations when the object path is used for integration
  rather than local download response naming.
- SFTP, FTP, shared directory, or batch import/export paths with business
  integration semantics.
- File-producing or file-consuming jobs that exchange data with another system.

## Identifier

- Prefer `scheme_or_provider bucket/path` or a stable semantic file path.
- Keep unresolved config references as `{config.key}/path`.
- Store operation details such as read/write/delete in metadata.

## Exclusions

- Mapper XML, templates, classpath resources, trace files, screenshots, local
  logs, browser download filenames, and generated reports are not FILE
  integration endpoints.
- If object storage is used as an SDK operation without shared-file integration
  semantics, classify it as a more specific `SDK` or `HTTP_CALL` only when
  justified by evidence.
