# auth.md

认证功能尚未开放（under construction / unavailable）。`available=false`，上线日期未公布。

这里描述未来的认证约定。注册、授权、账户认领、令牌交换以及保留的认证资源均返回 HTTP 503 `temporarily_unavailable`，不会创建账户或签发凭据。

[公开资料查询](https://fanqiang.guide/ai/)、[公开 API](https://fanqiang.guide/openapi.json) 和 [MCP](https://fanqiang.guide/mcp) 已开放，无需注册或登录。

```ilang
::ILANG::v5.0
::STATE{status:under_construction; available:false; capabilities_status:planned_contract_only; launch_date:not_announced}
::MODULE{AUTHENTICATION_STATUS}
  [MUST] Treat the listed authentication operations as planned and unavailable.
  [MUST] Do not submit identity data, passwords, assertions or tokens to these endpoints while available=false.
  [MUST] Expect HTTP 503 temporarily_unavailable. No account, assertion, claim or token will be created.
  [MUST] Use the unauthenticated reference at https://fanqiang.guide/ai/, read-only API at https://fanqiang.guide/openapi.json or MCP at https://fanqiang.guide/mcp.
  [MUST] Keep public lookup unauthenticated. These future declarations do not change its access rules.
  [MUST] Do not infer or promise a launch date.
::MODULE{PLANNED_AUTH_CONTRACT}
  oauth:authorization_code; pkce:S256; scope:library:read
  anonymous:planned_identity_assertion_then_JWT_bearer_exchange; final_credential:access_token
  registration_uri:https://fanqiang.guide/agent-auth/register
  claim_uri:https://fanqiang.guide/agent-auth/claim
  [MUST] Interpret all grants and credential types as future design only, never current acceptance.
::ILANG::COMPLETE::
```
