# Trace

## Understanding

The HTTP_CALL rule already required config base URL plus static path identifiers
such as `METHOD {configKey}/path`, but scanner behavior still collapsed some
real calls to the base config key only.

Observed real source patterns:

- `kyLinApiConfig.getMbspApiUrl(KyLinMbspApiPathConsts.Member.MEMBER_POST_REGISTER_WECHAT)`
- `kyLinApiConfig.getCustomerUrl(KyLinApiPathConsts.DataReport.GUIDE_DAT_REPORT)`
- `kyLinApiConfig.getEbrandMemberUrl(KyLinMbspApiPathConsts.Member.MEMBER_GET_MOBILE_ENCRYPT)`

## Iteration 1

Patch:

- Extended `JAVA_CONFIG_GETTER_ASSIGN_RE` to capture getter arguments.
- Added `config_placeholder_with_path(...)`.
- Added fixture `ConfigBaseUrlClient.java`.
- Added verifier expectations for config base URL plus static path.

Fixture result:

- `endpoint_taxonomy` verifier PASS.

Full siyu-develop result:

- Scanner emitted 1923 endpoints and 6 services.
- Verifier FAIL.

Failures:

- Missing `POST {kyLinApiConfig.mbspApiUrl}/member/register/wechat`.
- Missing `GET {kyLinApiConfig.customerUrl}/data/report/guide`.

## Iteration 2

Contrast:

- Fixture used unique leaf constants.
- Real source uses nested constants like
  `KyLinMbspApiPathConsts.Member.MEMBER_POST_REGISTER_WECHAT`.
- Different classes define the same leaf constant name, so leaf-only lookup is
  ambiguous.

Patch:

- Added qualified owner-head constant fallback in `resolve_java_expr(...)`.
- Split fixture expectations from siyu-specific public-source regression
  expectations.

Fixture result:

- `endpoint_taxonomy` verifier PASS.

Full siyu-develop result:

- Scanner emitted 1932 endpoints and 6 services.
- Verifier PASS.

Representative new HTTP_CALL identifiers:

- `POST {kyLinApiConfig.customerUrl}/guide/guide/dataQuotaByCode`
- `POST {kyLinApiConfig.mbspApiUrl}/member/register`
- `POST {kyLinApiConfig.customerUrl}/wechat/member/register`
- `POST {kyLinApiConfig.mbspApiUrl}/member/modify`
- `POST {kyLinApiConfig.ebrandMemberUrl}/mobile/encryption`
