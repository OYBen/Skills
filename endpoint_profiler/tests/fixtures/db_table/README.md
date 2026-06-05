# DB_TABLE Fixture

This fixture covers the database table rules:

- model metadata JSON should produce `DB_TABLE customer_info` and a related
  `DATAMODEL` endpoint.
- guide-package style model metadata such as
  `data.prctvmkt.${memberProgramCode}.Guide` must preserve the full FQN as the
  `DATAMODEL` identifier.
- production Mapper annotation should produce `DB_TABLE t_user`.
- production Mapper XML should produce `DB_TABLE customer_info`.
- test SQL under `src/test` must not produce `DB_TABLE` endpoints.
- `RedPacketCallBackRepository` must not produce `DATAMODEL RedPacketCallBack`;
  the entity `@TableName("red_packet_call_back")` is `DB_TABLE` evidence.
- `CemController` should produce `HTTP_API POST /cem/event`, not `ANY cem` or
  `POST event`.

Run:

```powershell
python scripts/endpoint_profiler.py tests/fixtures/db_table/source --out tests/fixtures/db_table/out
python scripts/verify_endpoint_profiler.py tests/fixtures/db_table/out
```
