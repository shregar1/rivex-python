# Rivex-Py Docstring Tracker

Tracking the rollout of Google-style docstrings across all non-dunder functions
in `rivex-py/src/rivex/`. Generated from AST scan; the canonical list is at the
bottom of this file.

## Docstring template

One-line summary, then a longer description, then `Args:`, `Returns:` (when the
function returns something other than `None`), `Raises:` (when applicable), and
`Example:` (for non-trivial public API). For classes, swap `Args:` for an
`Attributes:` block plus a `Parameters:` block on `__init__` if present.

```python
def function_name(arg1: int, arg2: str = "x") -> bool:
    """One-line summary of what this function does.

    A longer description of the behavior, side effects, and how it fits
    into the larger system. Mention anything a caller must know before
    using it (required setup, thread-safety, mutation, performance).

    Args:
        arg1: What this argument controls.
        arg2: What this argument controls. Defaults to "x".

    Returns:
        What the function returns and when.

    Raises:
        ValueError: When and why this is raised.

    Example:
        >>> function_name(1)
        True
    """
    ...
```

## Conventions

- Do not add docstrings to dunder methods (`__init__`, `__repr__`, etc.).
- Keep the first line a single self-contained sentence ending in a period.
- Reuse the existing module/class `__all__` for cross-reference; do not invent new symbols.
- Reference concrete types from the function signature verbatim — do not restate the type if the signature already declares it.
- Prefer "this middleware" / "this handler" over "the function" for prose clarity.

## Progress

- Total non-dunder functions: **1843**
- Need docstring: **1203**
- Files covered: **265**

## Function inventory

Format per entry: `- [ ] \`path:line\` qualname` (or `[x]` when complete).

### `_rust.py`

- [ ] `_rust.py:33` _missing
- [ ] `_rust.py:34` _stub

### `ai/agent.py`

- [x] `ai/agent.py:76` Agent.clear_memory
- [x] `ai/agent.py:80` Agent._build_tool_defs
- [x] `ai/agent.py:113` Agent._execute_tool
- [x] `ai/agent.py:121` async Agent.run
- [x] `ai/agent.py:168` async Agent.stream

### `ai/mcp_server.py`

- [x] `ai/mcp_server.py:78` MCPServer._register_endpoint
- [x] `ai/mcp_server.py:82` handle_mcp_request
- [x] `ai/mcp_server.py:106` mcp_info
- [x] `ai/mcp_server.py:121` MCPServer._dispatch
- [x] `ai/mcp_server.py:148` MCPServer._call_tool
- [x] `ai/mcp_server.py:159` MCPServer._read_resource
- [x] `ai/mcp_server.py:171` MCPServer._get_prompt
- [x] `ai/mcp_server.py:183` MCPServer._match_uri
- [x] `ai/mcp_server.py:222` MCPServer.tool
- [x] `ai/mcp_server.py:235` decorator
- [x] `ai/mcp_server.py:249` MCPServer.resource
- [x] `ai/mcp_server.py:266` decorator
- [x] `ai/mcp_server.py:283` MCPServer.prompt
- [x] `ai/mcp_server.py:296` decorator
- [x] `ai/mcp_server.py:311` MCPServer._build_tool_schema
- [x] `ai/mcp_server.py:348` MCPServer._build_prompt_schema

### `ai/providers.py`

- [x] `ai/providers.py:43` Provider.name
- [x] `ai/providers.py:48` async Provider.complete
- [x] `ai/providers.py:72` async Provider.stream
- [x] `ai/providers.py:93` async Provider.complete_with_tools
- [x] `ai/providers.py:133` OpenAIProvider.name
- [x] `ai/providers.py:136` OpenAIProvider._get_client
- [x] `ai/providers.py:147` async OpenAIProvider.complete
- [x] `ai/providers.py:177` async OpenAIProvider.stream
- [x] `ai/providers.py:205` async OpenAIProvider.complete_with_tools
- [x] `ai/providers.py:256` AnthropicProvider.name
- [x] `ai/providers.py:259` AnthropicProvider._get_client
- [x] `ai/providers.py:266` async AnthropicProvider.complete
- [x] `ai/providers.py:288` async AnthropicProvider.stream

### `ai/streaming.py`

- [x] `ai/streaming.py:36` stream_completion
- [x] `ai/streaming.py:82` async _produce

### `applications/applications.py`

- [x] `applications/applications.py:19` _make_hook_middleware
- [ ] `applications/applications.py:34` async _HookMiddleware.process
- [x] `applications/applications.py:66` _run_coroutine_sync
- [ ] `applications/applications.py:105` _worker
- [x] `applications/applications.py:308` Rivex.get
- [x] `applications/applications.py:321` Rivex.post
- [x] `applications/applications.py:325` Rivex.put
- [x] `applications/applications.py:329` Rivex.delete
- [x] `applications/applications.py:333` Rivex.patch
- [x] `applications/applications.py:337` Rivex.head
- [x] `applications/applications.py:341` Rivex.options
- [x] `applications/applications.py:347` Rivex.add_const_route
- [x] `applications/applications.py:390` Rivex._route
- [ ] `applications/applications.py:449` decorator
- [ ] `applications/applications.py:479` Rivex.url_for
- [ ] `applications/applications.py:489` Rivex.routes
- [ ] `applications/applications.py:492` Rivex.group
- [ ] `applications/applications.py:511` Rivex.websocket
- [ ] `applications/applications.py:512` decorator
- [x] `applications/applications.py:520` Rivex.sse
- [x] `applications/applications.py:542` _coerce_sse
- [ ] `applications/applications.py:547` async _awrap
- [ ] `applications/applications.py:557` _wrap
- [ ] `applications/applications.py:567` decorator
- [ ] `applications/applications.py:571` async sse_handler
- [x] `applications/applications.py:605` Rivex.mount
- [ ] `applications/applications.py:656` Rivex.register_plugin
- [ ] `applications/applications.py:665` Rivex.get_plugin
- [x] `applications/applications.py:670` Rivex.include_router
- [x] `applications/applications.py:750` Rivex.include_controller
- [x] `applications/applications.py:764` Rivex.include_route
- [x] `applications/applications.py:883` Rivex.security
- [x] `applications/applications.py:925` Rivex.security
- [x] `applications/applications.py:951` Rivex.db
- [ ] `applications/applications.py:963` Rivex.db
- [x] `applications/applications.py:966` Rivex.with_security
- [x] `applications/applications.py:1008` Rivex.add_middleware
- [x] `applications/applications.py:1059` Rivex.middleware
- [ ] `applications/applications.py:1066` decorator
- [ ] `applications/applications.py:1070` async _FuncMiddleware.process
- [ ] `applications/applications.py:1075` async _next
- [x] `applications/applications.py:1096` Rivex.before_request
- [x] `applications/applications.py:1112` Rivex.after_request
- [x] `applications/applications.py:1130` Rivex.after_response
- [x] `applications/applications.py:1144` Rivex.on_event
- [ ] `applications/applications.py:1154` decorator
- [x] `applications/applications.py:1165` Rivex.exception_handler
- [ ] `applications/applications.py:1177` decorator
- [x] `applications/applications.py:1185` Rivex.fallback
- [x] `applications/applications.py:1196` Rivex.run
- [x] `applications/applications.py:1260` Rivex._run_with_reload
- [x] `applications/applications.py:1280` Rivex._run_uvicorn
- [x] `applications/applications.py:1301` Rivex.run_async
- [x] `applications/applications.py:1338` Rivex._run_async_multi_process
- [x] `applications/applications.py:1388` Rivex._pickle_artifact
- [x] `applications/applications.py:1402` Rivex._async_worker_entry
- [x] `applications/applications.py:1450` Rivex.run_sync
- [x] `applications/applications.py:1505` Rivex._run_rust_async_server
- [x] `applications/applications.py:1513` Rivex._run_rust_sync_server
- [x] `applications/applications.py:1522` Rivex._install_access_key_middleware_if_needed
- [x] `applications/applications.py:1541` Rivex._drive_rust_server
- [ ] `applications/applications.py:1573` async _track_before
- [ ] `applications/applications.py:1577` async _track_after
- [ ] `applications/applications.py:1694` async ws_wrapper
- [ ] `applications/applications.py:1716` async _mount_handler
- [ ] `applications/applications.py:1733` async _noop
- [ ] `applications/applications.py:1771` _signal_handler
- [ ] `applications/applications.py:1781` _graceful_stop
- [x] `applications/applications.py:1822` Rivex._mount_admin
- [x] `applications/applications.py:1869` Rivex._register_landing_route
- [ ] `applications/applications.py:1886` async _landing
- [ ] `applications/applications.py:1897` Rivex._register_openapi_routes
- [ ] `applications/applications.py:1920` async openapi_handler
- [ ] `applications/applications.py:1947` async docs_handler
- [ ] `applications/applications.py:1971` async redoc_handler
- [ ] `applications/applications.py:1992` async health_handler
- [ ] `applications/applications.py:2004` _make_k8s_handler
- [ ] `applications/applications.py:2005` async _handler
- [x] `applications/applications.py:2025` Rivex.template
- [x] `applications/applications.py:2057` Rivex.override_dependency
- [x] `applications/applications.py:2066` Rivex.clear_overrides
- [x] `applications/applications.py:2071` Rivex.override_scope
- [ ] `applications/applications.py:2089` Rivex._register_asyncapi_route
- [ ] `applications/applications.py:2103` async asyncapi_handler
- [ ] `applications/applications.py:2121` async asyncapi_docs_handler
- [x] `applications/applications.py:2132` Rivex._build_hook_middleware
- [ ] `applications/applications.py:2145` Rivex._apply_middleware
- [ ] `applications/applications.py:2150` Rivex._run_hooks
- [ ] `applications/applications.py:2158` Rivex._run_async
- [ ] `applications/applications.py:2161` Rivex._enter_lifespan
- [ ] `applications/applications.py:2189` Rivex._exit_lifespan

### `auth/abstraction.py`

- [x] `auth/abstraction.py:16` async IAuthProvider.authenticate
- [x] `auth/abstraction.py:25` async IAuthGuard.check_permissions

### `auth/auth.py`

- [x] `auth/auth.py:57` _extract_auth_from_request_data
- [x] `auth/auth.py:73` _build_jwt_wrapper
- [x] `auth/auth.py:82` async jwt_wrapper
- [x] `auth/auth.py:109` set_user_resolver
- [x] `auth/auth.py:120` get_user_resolver
- [x] `auth/auth.py:125` current_user
- [x] `auth/auth.py:137` _find_request
- [x] `auth/auth.py:154` _stash_user
- [x] `auth/auth.py:163` authenticated
- [x] `auth/auth.py:188` _decorator
- [x] `auth/auth.py:192` async wrapper
- [x] `auth/auth.py:241` admin_only
- [x] `auth/auth.py:255` get_jwt_claims
- [x] `auth/auth.py:273` _b64_decode
- [x] `auth/auth.py:278` _decode_jwt_payload
- [x] `auth/auth.py:292` jwt_required
- [x] `auth/auth.py:319` _verify
- [x] `auth/auth.py:362` decorator

### `auth/crypto.py`

- [x] `auth/crypto.py:23` aes_gcm_encrypt
- [x] `auth/crypto.py:27` aes_gcm_decrypt

### `auth/data_protection.py`

- [x] `auth/data_protection.py:32` DataProtector.rotate_key
- [x] `auth/data_protection.py:40` DataProtector.protect_raw
- [x] `auth/data_protection.py:48` DataProtector.unprotect_raw
- [x] `auth/data_protection.py:66` DataProtector.protect
- [x] `auth/data_protection.py:79` DataProtector.unprotect

### `auth/guards.py`

- [x] `auth/guards.py:67` async GuardMiddleware.process

### `auth/jwt.py`

- [x] `auth/jwt.py:29` encode
- [x] `auth/jwt.py:62` _b64
- [x] `auth/jwt.py:65` _b64b
- [x] `auth/jwt.py:78` decode

### `auth/oidc.py`

- [x] `auth/oidc.py:75` OIDCAuth._fetch_jwks
- [x] `auth/oidc.py:96` OIDCAuth._get_key
- [x] `auth/oidc.py:102` OIDCAuth.discover
- [x] `auth/oidc.py:119` OIDCAuth.verify_token
- [x] `auth/oidc.py:191` OIDCAuth.require_auth
- [x] `auth/oidc.py:197` auth_middleware
- [x] `auth/oidc.py:231` OIDCAuth.depends_user
- [x] `auth/oidc.py:241` _get_user

### `auth/password_reset.py`

- [x] `auth/password_reset.py:34` PasswordReset.generate_token
- [x] `auth/password_reset.py:42` PasswordReset.validate_token
- [x] `auth/password_reset.py:59` async PasswordReset.send_reset_email
- [x] `auth/password_reset.py:107` PasswordResetMiddleware.get_user_by_email
- [x] `auth/password_reset.py:110` PasswordResetMiddleware.set_password
- [x] `auth/password_reset.py:113` PasswordResetMiddleware.register_routes
- [x] `auth/password_reset.py:114` async form_get
- [x] `auth/password_reset.py:117` async form_post
- [x] `auth/password_reset.py:125` async reset_get
- [x] `auth/password_reset.py:131` async reset_post

### `auth/permissions.py`

- [x] `auth/permissions.py:26` User.has_perm
- [x] `auth/permissions.py:34` User.has_role
- [x] `auth/permissions.py:39` User.has_perms
- [x] `auth/permissions.py:61` Permission.check
- [x] `auth/permissions.py:77` ModelPermission.check
- [x] `auth/permissions.py:91` ObjectPermissionBackend.has_perm
- [x] `auth/permissions.py:94` ObjectPermissionBackend.get_perms
- [x] `auth/permissions.py:99` RoleBasedBackend.has_perm
- [x] `auth/permissions.py:106` RoleBasedBackend.get_perms
- [x] `auth/permissions.py:117` register_permission_backend
- [x] `auth/permissions.py:121` register_permission
- [x] `auth/permissions.py:132` permission_required
- [x] `auth/permissions.py:149` decorator
- [x] `auth/permissions.py:151` async wrapper
- [x] `auth/permissions.py:171` has_permission
- [x] `auth/permissions.py:196` async PermissionsMiddleware.process

### `auth/security.py`

- [x] `auth/security.py:264` OAuth2PasswordRequestForm._from_request
- [x] `auth/security.py:273` _first

### `auth/social_auth.py`

- [x] `auth/social_auth.py:19` SocialAuthConfig.provider
- [x] `auth/social_auth.py:53` SocialAuthMiddleware.on_login
- [x] `auth/social_auth.py:56` SocialAuthMiddleware._get_provider
- [x] `auth/social_auth.py:62` SocialAuthMiddleware._generate_state
- [x] `auth/social_auth.py:65` SocialAuthMiddleware._authorize_url
- [x] `auth/social_auth.py:76` async SocialAuthMiddleware._exchange_code
- [x] `auth/social_auth.py:101` async SocialAuthMiddleware._get_user_info
- [x] `auth/social_auth.py:119` SocialAuthMiddleware.register_routes
- [x] `auth/social_auth.py:124` async login_route
- [x] `auth/social_auth.py:129` async callback_route

### `autodiscovery.py`

- [x] `autodiscovery.py:17` autodiscover

### `cli/bench.py`

- [x] `cli/bench.py:18` run_bench
- [x] `cli/bench.py:42` make_request
- [x] `cli/bench.py:96` _percentile
- [x] `cli/bench.py:101` _ms

### `cli/cli.py`

- [x] `cli/cli.py:8` main
- [x] `cli/cli.py:300` _import_app
- [x] `cli/cli.py:324` _run_management
- [x] `cli/cli.py:348` _print_routes
- [x] `cli/cli.py:382` _export_openapi
- [x] `cli/cli.py:409` load_env_file
- [x] `cli/cli.py:440` _run_with_reload
- [x] `cli/cli.py:471` _scan_mtimes
- [x] `cli/cli.py:553` _run_dev
- [x] `cli/cli.py:586` _run_test

### `cli/dev_repl.py`

- [x] `cli/dev_repl.py:11` start_repl

### `cli/inspector.py`

- [x] `cli/inspector.py:50` Inspector._register_routes
- [x] `cli/inspector.py:53` _make_handler
- [x] `cli/inspector.py:54` handler
- [x] `cli/inspector.py:71` Inspector._handle
- [x] `cli/inspector.py:86` decorator
- [x] `cli/inspector.py:94` Inspector._check_auth

### `cli/management.py`

- [x] `cli/management.py:23` BaseCommand.add_arguments
- [x] `cli/management.py:26` BaseCommand.handle
- [x] `cli/management.py:29` BaseCommand.run_from_argv
- [x] `cli/management.py:37` BaseCommand.get_version
- [x] `cli/management.py:41` register_command
- [x] `cli/management.py:45` get_command
- [x] `cli/management.py:49` get_all_commands
- [x] `cli/management.py:53` discover_commands
- [x] `cli/management.py:70` add_management_subcommands
- [x] `cli/management.py:86` CreateGroupCommand.add_arguments
- [x] `cli/management.py:90` CreateGroupCommand.handle
- [x] `cli/management.py:102` ListGroupsCommand.handle
- [x] `cli/management.py:116` CollectStaticCommand.add_arguments
- [x] `cli/management.py:120` CollectStaticCommand.handle
- [x] `cli/management.py:144` MakeMessagesCommand.add_arguments
- [x] `cli/management.py:150` MakeMessagesCommand.handle
- [x] `cli/management.py:187` CompileMessagesCommand.add_arguments
- [x] `cli/management.py:191` CompileMessagesCommand.handle

### `cli/plugins.py`

- [x] `cli/plugins.py:83` Plugin.install
- [x] `cli/plugins.py:86` Plugin.uninstall
- [x] `cli/plugins.py:97` load_plugins

### `cli/reload.py`

- [x] `cli/reload.py:34` _snapshot
- [x] `cli/reload.py:68` _spawn_child
- [x] `cli/reload.py:76` _terminate
- [x] `cli/reload.py:90` run_with_reload

### `config/settings.py`

- [x] `config/settings.py:51` _parse_env_file
- [x] `config/settings.py:90` Settings._build_env
- [x] `config/settings.py:101` Settings._collect_values
- [ ] `config/settings.py:113` _normalise
- [x] `config/settings.py:141` Settings.from_env
- [x] `config/settings.py:153` Settings.from_dict

### `constants/__init__.py`

- [x] `constants/__init__.py:111` ResponseStatus.from_http

### `constants/abstraction.py`

- [x] `constants/abstraction.py:19` IConstant.values
- [x] `constants/abstraction.py:28` IConstant.keys
- [x] `constants/abstraction.py:37` IConstant.is_valid

### `constants/api/envelope.py`

- [x] `constants/api/envelope.py:24` ApiStatus.label
- [x] `constants/api/envelope.py:47` ApiResponseKey.label

### `constants/api/http_method.py`

- [x] `constants/api/http_method.py:33` HTTPMethod.all_methods
- [x] `constants/api/http_method.py:38` HTTPMethod.parse
- [x] `constants/api/http_method.py:48` HTTPMethod.is_mutating

### `constants/api/media_type.py`

- [x] `constants/api/media_type.py:72` MediaType.is_body_type

### `constants/api/request_entity.py`

- [x] `constants/api/request_entity.py:28` RequestEntity.label

### `constants/api/response_entity.py`

- [x] `constants/api/response_entity.py:23` ResponseEntity.label

### `constants/crypto/encryption.py`

- [x] `constants/crypto/encryption.py:32` Encryption.label

### `constants/crypto/hashing.py`

- [x] `constants/crypto/hashing.py:20` Hashing.label

### `constants/db.py`

- [x] `constants/db.py:29` AuditColumn.label

### `constants/encoding/__init__.py`

- [x] `constants/encoding/__init__.py:23` Encoding.label
- [x] `constants/encoding/__init__.py:37` ContentEncoding.label
- [x] `constants/encoding/__init__.py:53` HashAlgorithm.label

### `constants/environment.py`

- [x] `constants/environment.py:19` Environment.label

### `constants/jwt.py`

- [x] `constants/jwt.py:22` JWT.label

### `constants/lookup/mime_type.py`

- [x] `constants/lookup/mime_type.py:35` MimeType.label

### `constants/otp.py`

- [x] `constants/otp.py:11` otp_alphabet_regex
- [x] `constants/otp.py:16` otp_passphrase_regex
- [x] `constants/otp.py:130` OTP.alphabet_regex
- [x] `constants/otp.py:135` OTP.passphrase_regex
- [x] `constants/otp.py:148` OTP.label

### `constants/regex/abstraction.py`

- [x] `constants/regex/abstraction.py:20` IRegexConstant.compile_patterns

### `constants/regex/injection.py`

- [x] `constants/regex/injection.py:27` InjectionRegex.has_xss
- [x] `constants/regex/injection.py:32` InjectionRegex.has_sqli

### `constants/regex/patterns.py`

- [x] `constants/regex/patterns.py:109` Regex.compile_patterns
- [x] `constants/regex/patterns.py:122` Regex.label

### `constants/regex/pii.py`

- [x] `constants/regex/pii.py:23` PiiRegex.is_ssn
- [x] `constants/regex/pii.py:28` PiiRegex.is_card

### `constants/regex/security_key.py`

- [x] `constants/regex/security_key.py:23` SecurityKeyRegex.is_sensitive_key
- [x] `constants/regex/security_key.py:28` SecurityKeyRegex.matches_value

### `context/context.py`

- [x] `context/context.py:49` request_context
- [ ] `context/context.py:56` current_user_id
- [ ] `context/context.py:60` current_ip
- [ ] `context/context.py:64` current_user_agent
- [ ] `context/context.py:68` current_request_id
- [x] `context/context.py:72` bind_user
- [x] `context/context.py:83` bind_extra
- [ ] `context/context.py:104` async RequestContextMiddleware.process

### `contrib/uvicorn.py`

- [x] `contrib/uvicorn.py:59` serve
- [x] `contrib/uvicorn.py:170` make_asgi_app
- [x] `contrib/uvicorn.py:190` _resolve_asgi_app

### `data/caching.py`

- [ ] `data/caching.py:17` _serialize
- [ ] `data/caching.py:22` _serialize
- [ ] `data/caching.py:26` _md5_etag
- [ ] `data/caching.py:34` _etag_match
- [ ] `data/caching.py:49` async CacheMiddleware.process
- [ ] `data/caching.py:95` CacheMiddleware._make_key
- [ ] `data/caching.py:104` async ETagMiddleware.process
- [ ] `data/caching.py:154` _CachedWrapper._is_stale
- [ ] `data/caching.py:261` _CachedWrapper.cache_clear
- [ ] `data/caching.py:267` cached_response
- [ ] `data/caching.py:271` cached_response
- [x] `data/caching.py:274` cached_response
- [ ] `data/caching.py:279` decorator

### `data/pagination.py`

- [ ] `data/pagination.py:20` Page.pages
- [ ] `data/pagination.py:26` Page.has_next
- [ ] `data/pagination.py:30` Page.has_previous
- [ ] `data/pagination.py:33` Page.dict
- [ ] `data/pagination.py:64` CursorPage.dict
- [x] `data/pagination.py:83` paginate

### `data/search.py`

- [ ] `data/search.py:11` async SearchBackend.index
- [ ] `data/search.py:15` async SearchBackend.remove
- [ ] `data/search.py:19` async SearchBackend.search
- [ ] `data/search.py:24` async SearchBackend.reindex
- [ ] `data/search.py:28` async SearchBackend.delete_index
- [ ] `data/search.py:44` PostgresSearchBackend._tsquery
- [ ] `data/search.py:48` PostgresSearchBackend._tsvector
- [ ] `data/search.py:51` async PostgresSearchBackend.index
- [ ] `data/search.py:66` async PostgresSearchBackend.remove
- [ ] `data/search.py:71` async PostgresSearchBackend.search
- [ ] `data/search.py:90` async PostgresSearchBackend.reindex
- [ ] `data/search.py:95` async PostgresSearchBackend.delete_index
- [ ] `data/search.py:121` async ElasticsearchBackend.index
- [ ] `data/search.py:125` async ElasticsearchBackend.remove
- [ ] `data/search.py:132` async ElasticsearchBackend.search
- [ ] `data/search.py:148` async ElasticsearchBackend.reindex
- [ ] `data/search.py:153` async ElasticsearchBackend.delete_index

### `data/versioning.py`

- [ ] `data/versioning.py:12` BaseVersioning.determine_version
- [ ] `data/versioning.py:21` URLPathVersioning.determine_version
- [ ] `data/versioning.py:34` HeaderVersioning.determine_version
- [ ] `data/versioning.py:44` QueryParamVersioning.determine_version
- [ ] `data/versioning.py:58` AcceptHeaderVersioning.determine_version
- [ ] `data/versioning.py:79` async VersionMiddleware.process

### `datastructures/bloom.py`

- [x] `datastructures/bloom.py:23` BloomFilter.add
- [x] `datastructures/bloom.py:29` BloomFilter.contains

### `datastructures/headers.py`

- [x] `datastructures/headers.py:26` Headers.get
- [x] `datastructures/headers.py:36` Headers.getlist
- [x] `datastructures/headers.py:42` Headers.keys
- [x] `datastructures/headers.py:47` Headers.values
- [x] `datastructures/headers.py:52` Headers.items

### `datastructures/ring_buffer.py`

- [x] `datastructures/ring_buffer.py:27` RingBuffer.push
- [x] `datastructures/ring_buffer.py:33` RingBuffer.pop

### `db/__init__.py`

- [x] `db/__init__.py:44` register_driver
- [x] `db/__init__.py:48` _detect_driver
- [x] `db/__init__.py:89` DatabaseConfig.min_size
- [x] `db/__init__.py:93` DatabaseConfig.max_size
- [x] `db/__init__.py:112` async DatabasePool.connect
- [x] `db/__init__.py:115` async DatabasePool.disconnect
- [x] `db/__init__.py:119` async DatabasePool.acquire
- [x] `db/__init__.py:131` async DatabasePool.create
- [x] `db/__init__.py:153` DatabaseRegistry.configure
- [x] `db/__init__.py:163` DatabaseRegistry._ensure_connected
- [x] `db/__init__.py:171` DatabaseRegistry.pool
- [x] `db/__init__.py:178` async DatabaseRegistry.connect_all
- [x] `db/__init__.py:199` async DatabaseRegistry.disconnect_all

### `db/automigrate.py`

- [x] `db/automigrate.py:25` async AutoMigrator._get_existing_tables
- [x] `db/automigrate.py:40` async AutoMigrator._get_table_columns
- [x] `db/automigrate.py:62` async AutoMigrator.detect_changes
- [x] `db/automigrate.py:120` AutoMigrator._col_to_sql
- [x] `db/automigrate.py:126` AutoMigrator.generate_sql
- [x] `db/automigrate.py:139` async AutoMigrator.write_migration
- [x] `db/automigrate.py:150` async AutoMigrator.apply
- [x] `db/automigrate.py:162` AutoMigrator.print_plan

### `db/migrations.py`

- [x] `db/migrations.py:72` Migrator._discover
- [x] `db/migrations.py:120` async Migrator._ensure_table
- [x] `db/migrations.py:146` async Migrator._applied
- [x] `db/migrations.py:157` async Migrator.up
- [x] `db/migrations.py:177` async Migrator.down
- [x] `db/migrations.py:204` async Migrator.history
- [x] `db/migrations.py:214` async Migrator._run_sql
- [x] `db/migrations.py:225` async Migrator._mark_applied
- [x] `db/migrations.py:239` async Migrator._mark_reverted
- [x] `db/migrations.py:252` async Migrator.alembic_upgrade
- [x] `db/migrations.py:260` async Migrator.alembic_downgrade
- [x] `db/migrations.py:263` async Migrator.alembic_revision
- [x] `db/migrations.py:272` _run_alembic

### `db/router.py`

- [x] `db/router.py:23` DatabaseRouter.db_for_read
- [x] `db/router.py:27` DatabaseRouter.db_for_write
- [x] `db/router.py:31` DatabaseRouter.allow_migrate
- [x] `db/router.py:35` DatabaseRouter.allow_relation
- [x] `db/router.py:46` RouterRegistry.add
- [x] `db/router.py:49` RouterRegistry.remove
- [x] `db/router.py:53` RouterRegistry.db_for_read
- [x] `db/router.py:60` RouterRegistry.db_for_write
- [x] `db/router.py:67` RouterRegistry.allow_migrate
- [x] `db/router.py:74` RouterRegistry.allow_relation
- [x] `db/router.py:82` using
- [x] `db/router.py:91` decorator
- [x] `db/router.py:93` async wrapper

### `db/sqlite.py`

- [x] `db/sqlite.py:25` async SqlitePool.connect
- [x] `db/sqlite.py:32` async SqlitePool.disconnect
- [x] `db/sqlite.py:38` async SqlitePool.acquire
- [x] `db/sqlite.py:49` async SqlitePool.fetch
- [x] `db/sqlite.py:54` async SqlitePool.execute

### `db/transactions.py`

- [x] `db/transactions.py:75` async Transaction._commit_internal
- [x] `db/transactions.py:81` async Transaction._rollback_internal
- [x] `db/transactions.py:87` async Transaction.commit
- [x] `db/transactions.py:91` async Transaction.rollback
- [x] `db/transactions.py:95` async Transaction.savepoint
- [x] `db/transactions.py:101` async Transaction.rollback_to_savepoint
- [x] `db/transactions.py:104` async Transaction.release_savepoint
- [x] `db/transactions.py:143` async wrapper

### `di/_injection.py`

- [x] `di/_injection.py:61` _get_cached_signature
- [x] `di/_injection.py:81` _build_codegen_wrapper
- [x] `di/_injection.py:297` async _extract_depends
- [x] `di/_injection.py:307` _extract_path
- [x] `di/_injection.py:320` _extract_path_param
- [x] `di/_injection.py:340` _extract_query
- [x] `di/_injection.py:353` _extract_query_param
- [x] `di/_injection.py:382` _extract_header_param
- [x] `di/_injection.py:403` _extract_cookie_param
- [x] `di/_injection.py:424` _extract_body_param
- [x] `di/_injection.py:485` _extract_body_raw
- [x] `di/_injection.py:499` _extract_body
- [x] `di/_injection.py:515` async _extract_request
- [x] `di/_injection.py:521` async _extract_background_tasks
- [x] `di/_injection.py:525` _extract_file
- [x] `di/_injection.py:538` _extract_form
- [x] `di/_injection.py:558` _extract_form_model
- [x] `di/_injection.py:618` build_handler_wrapper
- [x] `di/_injection.py:653` async cached_wrapper
- [x] `di/_injection.py:668` async gen_wrapper
- [x] `di/_injection.py:753` async direct_wrapper
- [x] `di/_injection.py:803` async wrapper
- [x] `di/_injection.py:974` _http_exception_response
- [x] `di/_injection.py:983` _error_response
- [x] `di/_injection.py:989` _normalize_response_fast
- [x] `di/_injection.py:1083` _normalize_response
- [x] `di/_injection.py:1093` _apply_response_model
- [x] `di/_injection.py:1142` async _resolve_depends
- [x] `di/_injection.py:1252` _dependency_callable
- [x] `di/_injection.py:1272` _find_best_handler
- [x] `di/_injection.py:1284` async _call_handler
- [x] `di/_injection.py:1290` _is_request_type
- [x] `di/_injection.py:1299` _is_background_tasks_type
- [x] `di/_injection.py:1310` _is_strict_body_model
- [x] `di/_injection.py:1327` _is_body_model
- [x] `di/_injection.py:1362` _get_content_type
- [x] `di/_injection.py:1366` _coerce_optional_hint
- [x] `di/_injection.py:1385` _coerce
- [x] `di/_injection.py:1459` _parse_cookies

### `di/dependencies.py`

- [x] `di/dependencies.py:101` Dependency.resolve

### `di/params.py`

- [x] `di/params.py:116` _ParamBase.required
- [x] `di/params.py:120` _ParamBase.validate
- [x] `di/params.py:175` _ParamBase.openapi_schema_extra
- [x] `di/params.py:293` Header.header_name

### `dtos/abstraction.py`

- [x] `dtos/abstraction.py:17` IDTO.to_dict
- [x] `dtos/abstraction.py:21` IDTO.to_json

### `dtos/exception/abstraction.py`

- [x] `dtos/exception/abstraction.py:16` IExceptionDTO.to_dict

### `dtos/exception/validation_error.py`

- [ ] `dtos/exception/validation_error.py:32` ValidationErrorItem.to_dict
- [ ] `dtos/exception/validation_error.py:35` ValidationErrorItem.to_json

### `dtos/headers.py`

- [x] `dtos/headers.py:28` HeaderDTO.get
- [x] `dtos/headers.py:31` HeaderDTO.set
- [x] `dtos/headers.py:34` HeaderDTO.delete
- [x] `dtos/headers.py:37` HeaderDTO.to_dict
- [x] `dtos/headers.py:40` HeaderDTO.to_tuples
- [x] `dtos/headers.py:43` HeaderDTO.to_json
- [x] `dtos/headers.py:56` HeaderDTO.from_dict
- [x] `dtos/headers.py:60` HeaderDTO.from_tuples

### `dtos/response/abstraction.py`

- [x] `dtos/response/abstraction.py:23` IResponseDTO.status_code
- [x] `dtos/response/abstraction.py:27` IResponseDTO.to_headers
- [x] `dtos/response/abstraction.py:61` ResponseDTO.to_dict
- [x] `dtos/response/abstraction.py:84` ResponseDTO.to_json
- [x] `dtos/response/abstraction.py:89` ResponseDTO.failed
- [x] `dtos/response/abstraction.py:115` ResponseDTO.success
- [x] `dtos/response/abstraction.py:141` response_dto

### `dtos/response/content/html_response.py`

- [ ] `dtos/response/content/html_response.py:24` HtmlResponse.to_dict
- [ ] `dtos/response/content/html_response.py:27` HtmlResponse.to_json
- [ ] `dtos/response/content/html_response.py:30` HtmlResponse.to_body
- [ ] `dtos/response/content/html_response.py:33` HtmlResponse.to_headers

### `dtos/response/content/http_response.py`

- [x] `dtos/response/content/http_response.py:41` HTTPResponse.to_dict
- [x] `dtos/response/content/http_response.py:45` HTTPResponse.to_json
- [x] `dtos/response/content/http_response.py:51` HTTPResponse.to_headers
- [x] `dtos/response/content/http_response.py:58` HTTPResponse.ok
- [x] `dtos/response/content/http_response.py:84` HTTPResponse.fail
- [x] `dtos/response/content/http_response.py:111` HTTPResponse.from_exception

### `dtos/response/content/json_response.py`

- [ ] `dtos/response/content/json_response.py:24` JsonResponse.to_dict
- [ ] `dtos/response/content/json_response.py:29` JsonResponse.to_json
- [ ] `dtos/response/content/json_response.py:32` JsonResponse.to_headers

### `dtos/response/content/plain_text_response.py`

- [ ] `dtos/response/content/plain_text_response.py:24` PlainTextResponse.to_dict
- [ ] `dtos/response/content/plain_text_response.py:27` PlainTextResponse.to_json
- [ ] `dtos/response/content/plain_text_response.py:30` PlainTextResponse.to_body
- [ ] `dtos/response/content/plain_text_response.py:33` PlainTextResponse.to_headers

### `dtos/response/content/xml_response.py`

- [ ] `dtos/response/content/xml_response.py:24` XmlResponse.to_dict
- [ ] `dtos/response/content/xml_response.py:29` XmlResponse.to_json
- [ ] `dtos/response/content/xml_response.py:32` XmlResponse.to_body
- [ ] `dtos/response/content/xml_response.py:35` XmlResponse.to_headers

### `dtos/response/exception/abstraction.py`

- [x] `dtos/response/exception/abstraction.py:16` IExceptionResponseDTO.from_exception

### `dtos/response/exception/bad_gateway.py`

- [x] `dtos/response/exception/bad_gateway.py:16` BadGatewayExceptionResponse.from_bad_gateway_exception
- [ ] `dtos/response/exception/bad_gateway.py:39` BadGatewayExceptionResponse.from_exception

### `dtos/response/exception/bad_request.py`

- [x] `dtos/response/exception/bad_request.py:16` BadRequestExceptionResponse.from_bad_request_exception
- [ ] `dtos/response/exception/bad_request.py:39` BadRequestExceptionResponse.from_exception

### `dtos/response/exception/concurrency_conflict.py`

- [x] `dtos/response/exception/concurrency_conflict.py:16` ConcurrencyConflictExceptionResponse.from_concurrency_conflict_exception
- [ ] `dtos/response/exception/concurrency_conflict.py:39` ConcurrencyConflictExceptionResponse.from_exception

### `dtos/response/exception/conflict.py`

- [x] `dtos/response/exception/conflict.py:16` ConflictExceptionResponse.from_conflict_exception
- [ ] `dtos/response/exception/conflict.py:39` ConflictExceptionResponse.from_exception

### `dtos/response/exception/connection_failure.py`

- [x] `dtos/response/exception/connection_failure.py:16` ConnectionFailureExceptionResponse.from_connection_failure_exception
- [ ] `dtos/response/exception/connection_failure.py:39` ConnectionFailureExceptionResponse.from_exception

### `dtos/response/exception/constraint_violation.py`

- [x] `dtos/response/exception/constraint_violation.py:16` ConstraintViolationExceptionResponse.from_constraint_violation_exception
- [ ] `dtos/response/exception/constraint_violation.py:39` ConstraintViolationExceptionResponse.from_exception

### `dtos/response/exception/database_timeout.py`

- [x] `dtos/response/exception/database_timeout.py:16` DatabaseTimeoutExceptionResponse.from_database_timeout_exception
- [ ] `dtos/response/exception/database_timeout.py:39` DatabaseTimeoutExceptionResponse.from_exception

### `dtos/response/exception/duplicate_key.py`

- [x] `dtos/response/exception/duplicate_key.py:16` DuplicateKeyExceptionResponse.from_duplicate_key_exception
- [ ] `dtos/response/exception/duplicate_key.py:39` DuplicateKeyExceptionResponse.from_exception

### `dtos/response/exception/forbidden.py`

- [x] `dtos/response/exception/forbidden.py:16` ForbiddenExceptionResponse.from_forbidden_exception
- [ ] `dtos/response/exception/forbidden.py:39` ForbiddenExceptionResponse.from_exception

### `dtos/response/exception/generic.py`

- [x] `dtos/response/exception/generic.py:16` RivexExceptionResponse.from_rivex_exception
- [ ] `dtos/response/exception/generic.py:39` RivexExceptionResponse.from_exception

### `dtos/response/exception/internal_server_error.py`

- [x] `dtos/response/exception/internal_server_error.py:16` InternalServerExceptionResponse.from_internal_server_exception
- [ ] `dtos/response/exception/internal_server_error.py:39` InternalServerExceptionResponse.from_exception

### `dtos/response/exception/method_not_allowed.py`

- [x] `dtos/response/exception/method_not_allowed.py:16` MethodNotAllowedExceptionResponse.from_method_not_allowed_exception
- [ ] `dtos/response/exception/method_not_allowed.py:39` MethodNotAllowedExceptionResponse.from_exception

### `dtos/response/exception/not_found.py`

- [x] `dtos/response/exception/not_found.py:16` NotFoundExceptionResponse.from_not_found_exception
- [ ] `dtos/response/exception/not_found.py:39` NotFoundExceptionResponse.from_exception

### `dtos/response/exception/payload_too_large.py`

- [x] `dtos/response/exception/payload_too_large.py:16` PayloadTooLargeExceptionResponse.from_payload_too_large_exception
- [ ] `dtos/response/exception/payload_too_large.py:39` PayloadTooLargeExceptionResponse.from_exception

### `dtos/response/exception/service_unavailable.py`

- [x] `dtos/response/exception/service_unavailable.py:16` ServiceUnavailableExceptionResponse.from_service_unavailable_exception
- [ ] `dtos/response/exception/service_unavailable.py:39` ServiceUnavailableExceptionResponse.from_exception

### `dtos/response/exception/timeout.py`

- [x] `dtos/response/exception/timeout.py:16` TimeoutExceptionResponse.from_timeout_exception
- [ ] `dtos/response/exception/timeout.py:39` TimeoutExceptionResponse.from_exception

### `dtos/response/exception/too_many_requests.py`

- [x] `dtos/response/exception/too_many_requests.py:16` TooManyRequestsExceptionResponse.from_too_many_requests_exception
- [ ] `dtos/response/exception/too_many_requests.py:39` TooManyRequestsExceptionResponse.from_exception

### `dtos/response/exception/unauthenticated.py`

- [x] `dtos/response/exception/unauthenticated.py:16` UnauthenticatedExceptionResponse.from_unauthenticated_exception
- [ ] `dtos/response/exception/unauthenticated.py:39` UnauthenticatedExceptionResponse.from_exception

### `dtos/response/exception/unauthorized.py`

- [x] `dtos/response/exception/unauthorized.py:16` UnauthorizedExceptionResponse.from_unauthorized_exception
- [ ] `dtos/response/exception/unauthorized.py:39` UnauthorizedExceptionResponse.from_exception

### `dtos/response/exception/unprocessable_entity.py`

- [x] `dtos/response/exception/unprocessable_entity.py:16` UnprocessableEntityExceptionResponse.from_unprocessable_entity_exception
- [ ] `dtos/response/exception/unprocessable_entity.py:39` UnprocessableEntityExceptionResponse.from_exception

### `dtos/response/exception/unsupported_media_type.py`

- [x] `dtos/response/exception/unsupported_media_type.py:16` UnsupportedMediaTypeExceptionResponse.from_unsupported_media_type_exception
- [ ] `dtos/response/exception/unsupported_media_type.py:39` UnsupportedMediaTypeExceptionResponse.from_exception

### `dtos/response/stream/event_source_response.py`

- [x] `dtos/response/stream/event_source_response.py:24` EventSourceResponse.to_dict
- [x] `dtos/response/stream/event_source_response.py:27` EventSourceResponse.to_json
- [x] `dtos/response/stream/event_source_response.py:30` EventSourceResponse.to_headers

### `dtos/response/stream/streaming_response.py`

- [x] `dtos/response/stream/streaming_response.py:24` StreamingResponse.to_dict
- [x] `dtos/response/stream/streaming_response.py:27` StreamingResponse.to_json
- [x] `dtos/response/stream/streaming_response.py:30` StreamingResponse.to_headers

### `dtos/response/transfer/file_response.py`

- [x] `dtos/response/transfer/file_response.py:25` FileResponse.to_dict
- [x] `dtos/response/transfer/file_response.py:33` FileResponse.to_json
- [x] `dtos/response/transfer/file_response.py:36` FileResponse.to_headers

### `dtos/response/transfer/redirect_response.py`

- [x] `dtos/response/transfer/redirect_response.py:22` RedirectResponse.to_dict
- [x] `dtos/response/transfer/redirect_response.py:25` RedirectResponse.to_json
- [x] `dtos/response/transfer/redirect_response.py:28` RedirectResponse.to_headers

### `enums/abstraction.py`

- [x] `enums/abstraction.py:16` IEnum.values
- [x] `enums/abstraction.py:21` IEnum.names
- [x] `enums/abstraction.py:26` IEnum.is_valid

### `exceptions/__init__.py`

- [x] `exceptions/__init__.py:61` ExceptionUtils.is_rivex_exception

### `exceptions/abstraction.py`

- [x] `exceptions/abstraction.py:19` IException.to_response

### `exceptions/base.py`

- [x] `exceptions/base.py:25` ValidationErrorItem.to_dict
- [x] `exceptions/base.py:56` RivexException.with_errors
- [x] `exceptions/base.py:60` RivexException.with_details
- [x] `exceptions/base.py:64` RivexException.to_response

### `exceptions/http/exceptions.py`

- [x] `exceptions/http/exceptions.py:23` RequestValidationError.errors
- [x] `exceptions/http/exceptions.py:58` _default_phrase

### `exceptions/problem.py`

- [x] `exceptions/problem.py:29` ProblemDetail.to_dict
- [x] `exceptions/problem.py:38` ProblemDetail.to_bytes
- [x] `exceptions/problem.py:67` ProblemException.status_code
- [x] `exceptions/problem.py:77` ProblemResponse.create
- [x] `exceptions/problem.py:104` problem_exception_handler
- [x] `exceptions/problem.py:120` not_found
- [x] `exceptions/problem.py:126` bad_request
- [x] `exceptions/problem.py:132` unauthorized
- [x] `exceptions/problem.py:138` forbidden
- [x] `exceptions/problem.py:144` conflict
- [x] `exceptions/problem.py:148` unprocessable
- [x] `exceptions/problem.py:154` internal_error

### `flags.py`

- [ ] `flags.py:20` FlagContext.to_dict
- [ ] `flags.py:39` FlagDefinition.from_dict
- [ ] `flags.py:65` FlagRegistry.set_environment
- [ ] `flags.py:70` FlagRegistry.set
- [ ] `flags.py:89` FlagRegistry.clear
- [ ] `flags.py:94` FlagRegistry.snapshot
- [ ] `flags.py:97` FlagRegistry.is_enabled
- [ ] `flags.py:142` is_enabled

### `http/requests.py`

- [x] `http/requests.py:58` Request._from_raw
- [x] `http/requests.py:76` Request.headers
- [x] `http/requests.py:79` Request.header
- [x] `http/requests.py:83` Request.url
- [x] `http/requests.py:89` Request.content_type
- [x] `http/requests.py:93` Request.body
- [x] `http/requests.py:96` Request.body_json
- [x] `http/requests.py:127` async Request.json
- [x] `http/requests.py:131` Request.form
- [x] `http/requests.py:138` Request.text
- [x] `http/requests.py:142` Request.query_params
- [x] `http/requests.py:150` Request.cookies
- [x] `http/requests.py:157` Request.client
- [x] `http/requests.py:161` Request.base_url
- [x] `http/requests.py:166` async Request.stream
- [x] `http/requests.py:171` Request.htmx

### `http/responses.py`

- [x] `http/responses.py:25` Response.set_cookie
- [x] `http/responses.py:72` Response.delete_cookie
- [x] `http/responses.py:81` Response._to_raw
- [x] `http/responses.py:92` Response._render_body
- [x] `http/responses.py:116` JSONResponse._render_body
- [x] `http/responses.py:175` StreamingResponse._to_raw
- [x] `http/responses.py:197` StreamingResponse._render_body
- [x] `http/responses.py:201` async _collect
- [x] `http/responses.py:233` _worker
- [x] `http/responses.py:276` EventSourceResponse.format_event
- [x] `http/responses.py:325` FileResponse._render_body
- [x] `http/responses.py:329` FileResponse._to_raw

### `lifecycle/background.py`

- [x] `lifecycle/background.py:31` BackgroundTasks.add_task
- [x] `lifecycle/background.py:34` BackgroundTasks._run_all

### `lifecycle/broadcast.py`

- [x] `lifecycle/broadcast.py:26` ChannelLayer.add_channel
- [x] `lifecycle/broadcast.py:29` ChannelLayer.remove_channel
- [x] `lifecycle/broadcast.py:34` ChannelLayer.join_group
- [x] `lifecycle/broadcast.py:39` ChannelLayer.leave_group
- [x] `lifecycle/broadcast.py:43` async ChannelLayer.send
- [x] `lifecycle/broadcast.py:48` async ChannelLayer.group_send
- [x] `lifecycle/broadcast.py:53` async ChannelLayer.broadcast
- [x] `lifecycle/broadcast.py:57` ChannelLayer._redis_connected
- [x] `lifecycle/broadcast.py:60` async ChannelLayer.connect_redis
- [x] `lifecycle/broadcast.py:69` async ChannelLayer._redis_listener
- [x] `lifecycle/broadcast.py:85` async ChannelLayer.redis_publish
- [x] `lifecycle/broadcast.py:92` async ChannelLayer.close
- [x] `lifecycle/broadcast.py:116` async WebSocketChannel.send
- [x] `lifecycle/broadcast.py:126` async WebSocketChannel.receive
- [x] `lifecycle/broadcast.py:136` async WebSocketChannel.listen
- [x] `lifecycle/broadcast.py:144` async WebSocketChannel.close
- [x] `lifecycle/broadcast.py:168` WebSocketBroadcast.new_room
- [x] `lifecycle/broadcast.py:173` WebSocketBroadcast.delete_room
- [x] `lifecycle/broadcast.py:176` WebSocketBroadcast.join
- [x] `lifecycle/broadcast.py:186` WebSocketBroadcast.leave
- [x] `lifecycle/broadcast.py:193` async WebSocketBroadcast.broadcast
- [x] `lifecycle/broadcast.py:196` async WebSocketBroadcast.broadcast_all
- [x] `lifecycle/broadcast.py:199` async WebSocketBroadcast.to_user
- [x] `lifecycle/broadcast.py:204` WebSocketBroadcast.room_members
- [x] `lifecycle/broadcast.py:207` WebSocketBroadcast.active_rooms
- [x] `lifecycle/broadcast.py:218` async Room.broadcast
- [x] `lifecycle/broadcast.py:221` Room.member_count
- [x] `lifecycle/broadcast.py:224` Room.join
- [x] `lifecycle/broadcast.py:227` Room.leave

### `lifecycle/concurrency.py`

- [x] `lifecycle/concurrency.py:31` async run_in_threadpool

### `lifecycle/events.py`

- [x] `lifecycle/events.py:17` Signal.connect
- [x] `lifecycle/events.py:20` Signal.disconnect
- [x] `lifecycle/events.py:25` Signal.send
- [x] `lifecycle/events.py:51` async Signal.send_async
- [x] `lifecycle/events.py:63` Signal.receiver
- [x] `lifecycle/events.py:66` decorator

### `lifecycle/scheduler.py`

- [x] `lifecycle/scheduler.py:28` Scheduler.add_job
- [x] `lifecycle/scheduler.py:53` Scheduler.cron
- [x] `lifecycle/scheduler.py:66` decorator
- [x] `lifecycle/scheduler.py:77` Scheduler.every
- [x] `lifecycle/scheduler.py:88` decorator
- [x] `lifecycle/scheduler.py:93` Scheduler.scheduled
- [x] `lifecycle/scheduler.py:106` decorator
- [x] `lifecycle/scheduler.py:111` Scheduler.start
- [x] `lifecycle/scheduler.py:114` Scheduler.stop
- [x] `lifecycle/scheduler.py:117` Scheduler.list_jobs
- [x] `lifecycle/scheduler.py:120` Scheduler.pause_job
- [x] `lifecycle/scheduler.py:126` Scheduler.resume_job
- [x] `lifecycle/scheduler.py:132` Scheduler.delete_job

### `lifecycle/signals.py`

- [x] `lifecycle/signals.py:39` SignalBus.on
- [x] `lifecycle/signals.py:42` decorator
- [x] `lifecycle/signals.py:48` SignalBus.subscribe
- [x] `lifecycle/signals.py:52` SignalBus.unsubscribe
- [x] `lifecycle/signals.py:61` async SignalBus.emit
- [x] `lifecycle/signals.py:81` SignalBus.listeners
- [x] `lifecycle/signals.py:85` SignalBus.signals
- [x] `lifecycle/signals.py:89` SignalBus.clear

### `lifecycle/tasks.py`

- [x] `lifecycle/tasks.py:19` async TaskQueue.enqueue
- [x] `lifecycle/tasks.py:23` async TaskQueue.dequeue
- [x] `lifecycle/tasks.py:27` async TaskQueue.result
- [x] `lifecycle/tasks.py:31` async TaskQueue.length
- [x] `lifecycle/tasks.py:35` async TaskQueue.flush
- [x] `lifecycle/tasks.py:62` SimpleTaskQueue.register
- [x] `lifecycle/tasks.py:65` SimpleTaskQueue.handler
- [x] `lifecycle/tasks.py:66` decorator
- [x] `lifecycle/tasks.py:71` async SimpleTaskQueue.enqueue
- [x] `lifecycle/tasks.py:77` async SimpleTaskQueue.dequeue
- [x] `lifecycle/tasks.py:83` async SimpleTaskQueue.result
- [x] `lifecycle/tasks.py:93` async SimpleTaskQueue.length
- [x] `lifecycle/tasks.py:96` async SimpleTaskQueue.flush
- [x] `lifecycle/tasks.py:103` SimpleTaskQueue._worker_loop
- [x] `lifecycle/tasks.py:126` SimpleTaskQueue.start
- [x] `lifecycle/tasks.py:133` SimpleTaskQueue.stop
- [x] `lifecycle/tasks.py:145` async CeleryTaskQueue.enqueue
- [x] `lifecycle/tasks.py:149` async CeleryTaskQueue.dequeue
- [x] `lifecycle/tasks.py:152` async CeleryTaskQueue.result
- [x] `lifecycle/tasks.py:159` async CeleryTaskQueue.length
- [x] `lifecycle/tasks.py:162` async CeleryTaskQueue.flush
- [x] `lifecycle/tasks.py:172` async RQTaskQueue.enqueue
- [x] `lifecycle/tasks.py:177` async RQTaskQueue.dequeue
- [x] `lifecycle/tasks.py:180` async RQTaskQueue.result
- [x] `lifecycle/tasks.py:194` async RQTaskQueue.length
- [x] `lifecycle/tasks.py:197` async RQTaskQueue.flush
- [x] `lifecycle/tasks.py:201` task
- [x] `lifecycle/tasks.py:210` decorator
- [x] `lifecycle/tasks.py:216` async wrapper

### `middleware/_mw_utils.py`

- [x] `middleware/_mw_utils.py:8` apply_middleware_chain
- [ ] `middleware/_mw_utils.py:30` async make_handler

### `middleware/abstraction.py`

- [x] `middleware/abstraction.py:17` async IMiddleware.process

### `middleware/access_key.py`

- [ ] `middleware/access_key.py:60` AccessKeyMiddleware._read_header
- [ ] `middleware/access_key.py:67` AccessKeyMiddleware._reject
- [ ] `middleware/access_key.py:84` async AccessKeyMiddleware.process

### `middleware/access_log.py`

- [ ] `middleware/access_log.py:28` async AccessLogMiddleware.process

### `middleware/api_key_leak.py`

- [ ] `middleware/api_key_leak.py:26` _json_body
- [x] `middleware/api_key_leak.py:40` _normalize_allowed
- [ ] `middleware/api_key_leak.py:59` _path_matches
- [x] `middleware/api_key_leak.py:138` APIKeyLeakMiddleware._is_allowed
- [ ] `middleware/api_key_leak.py:153` APIKeyLeakMiddleware._value_is_secret
- [ ] `middleware/api_key_leak.py:163` APIKeyLeakMiddleware._key_is_secret
- [ ] `middleware/api_key_leak.py:169` APIKeyLeakMiddleware._redact
- [ ] `middleware/api_key_leak.py:188` async APIKeyLeakMiddleware.process

### `middleware/compression.py`

- [ ] `middleware/compression.py:27` async CompressionMiddleware.process

### `middleware/content_type.py`

- [ ] `middleware/content_type.py:50` async ContentTypeValidationMiddleware.process
- [ ] `middleware/content_type.py:83` ContentTypeValidationMiddleware._read_header
- [ ] `middleware/content_type.py:91` ContentTypeValidationMiddleware._is_excluded

### `middleware/cors.py`

- [ ] `middleware/cors.py:79` async CORSMiddleware.process
- [ ] `middleware/cors.py:98` CORSMiddleware._cors_headers

### `middleware/csrf.py`

- [ ] `middleware/csrf.py:33` async CSRFMiddleware.process
- [ ] `middleware/csrf.py:62` CSRFMiddleware._get_cookie_token
- [ ] `middleware/csrf.py:66` CSRFMiddleware._get_header_token
- [ ] `middleware/csrf.py:69` CSRFMiddleware._tokens_match
- [ ] `middleware/csrf.py:77` CSRFMiddleware._generate_token
- [ ] `middleware/csrf.py:89` CSRFMiddleware._forbidden

### `middleware/gzip.py`

- [x] `middleware/gzip.py:22` async GZipMiddleware.process

### `middleware/https_redirect.py`

- [ ] `middleware/https_redirect.py:16` async HTTPSRedirectMiddleware.process

### `middleware/idempotency.py`

- [ ] `middleware/idempotency.py:38` async IdempotencyMiddleware.process

### `middleware/injection_detection.py`

- [ ] `middleware/injection_detection.py:30` _json_body
- [x] `middleware/injection_detection.py:44` _walk_strings
- [ ] `middleware/injection_detection.py:62` _InjectionCheck.matches
- [ ] `middleware/injection_detection.py:69` _RegexInjectionCheck.matches
- [ ] `middleware/injection_detection.py:118` InjectionDetectionMiddleware._is_excluded
- [ ] `middleware/injection_detection.py:128` InjectionDetectionMiddleware._scan_string
- [ ] `middleware/injection_detection.py:134` InjectionDetectionMiddleware._scan_request
- [ ] `middleware/injection_detection.py:166` InjectionDetectionMiddleware._reject
- [ ] `middleware/injection_detection.py:188` async InjectionDetectionMiddleware.process
- [ ] `middleware/injection_detection.py:225` NoSQLInjectionDetectionMiddleware._is_excluded
- [ ] `middleware/injection_detection.py:235` NoSQLInjectionDetectionMiddleware._scan
- [ ] `middleware/injection_detection.py:250` NoSQLInjectionDetectionMiddleware._strip
- [ ] `middleware/injection_detection.py:261` async NoSQLInjectionDetectionMiddleware.process

### `middleware/ip_filter.py`

- [ ] `middleware/ip_filter.py:34` IPFilterMiddleware._is_blocked
- [ ] `middleware/ip_filter.py:48` async IPFilterMiddleware.process

### `middleware/max_body_size.py`

- [ ] `middleware/max_body_size.py:22` async MaxBodySizeMiddleware.process

### `middleware/method_override.py`

- [ ] `middleware/method_override.py:25` async MethodOverrideMiddleware.process

### `middleware/middleware.py`

- [ ] `middleware/middleware.py:18` async Middleware.process
- [ ] `middleware/middleware.py:67` async CORSMiddleware.process
- [ ] `middleware/middleware.py:90` CORSMiddleware._cors_headers
- [ ] `middleware/middleware.py:169` async RequestIdMiddleware.process
- [ ] `middleware/middleware.py:189` async GZipMiddleware.process
- [ ] `middleware/middleware.py:217` async TrustedHostMiddleware.process
- [ ] `middleware/middleware.py:237` async HTTPSRedirectMiddleware.process
- [ ] `middleware/middleware.py:264` async MaxBodySizeMiddleware.process
- [ ] `middleware/middleware.py:286` async AccessLogMiddleware.process
- [ ] `middleware/middleware.py:328` async SecurityHeadersMiddleware.process
- [ ] `middleware/middleware.py:344` async TrailingSlashMiddleware.process
- [ ] `middleware/middleware.py:375` async TimeoutMiddleware.process
- [ ] `middleware/middleware.py:398` IPFilterMiddleware._is_blocked
- [ ] `middleware/middleware.py:413` async IPFilterMiddleware.process
- [ ] `middleware/middleware.py:428` async CompressionMiddleware.process
- [ ] `middleware/middleware.py:490` async IdempotencyMiddleware.process
- [ ] `middleware/middleware.py:525` async MethodOverrideMiddleware.process

### `middleware/middleware_csp.py`

- [ ] `middleware/middleware_csp.py:76` CSPMiddleware._build_policy
- [ ] `middleware/middleware_csp.py:98` async CSPMiddleware.process

### `middleware/middleware_native.py`

- [ ] `middleware/middleware_native.py:84` SecurityHeadersMiddleware._apply
- [ ] `middleware/middleware_native.py:85` upsert
- [ ] `middleware/middleware_native.py:110` async SecurityHeadersMiddleware.process
- [ ] `middleware/middleware_native.py:140` RequestContextMiddleware._new_request_id
- [ ] `middleware/middleware_native.py:143` async RequestContextMiddleware.process
- [ ] `middleware/middleware_native.py:194` async RequestTimeoutMiddleware.process
- [ ] `middleware/middleware_native.py:241` RequestValidationMiddleware._violation
- [ ] `middleware/middleware_native.py:248` async RequestValidationMiddleware.process
- [ ] `middleware/middleware_native.py:310` async IdempotencyMiddleware.process
- [x] `middleware/middleware_native.py:390` ExceptionHandlerMiddleware._envelope_from_exception
- [ ] `middleware/middleware_native.py:431` async ExceptionHandlerMiddleware.process
- [ ] `middleware/middleware_native.py:445` _log_audit_now
- [ ] `middleware/middleware_native.py:470` AuditLoggerMiddleware._classify
- [ ] `middleware/middleware_native.py:477` async AuditLoggerMiddleware.process
- [ ] `middleware/middleware_native.py:551` AuthorizationMiddleware._claim_roles
- [ ] `middleware/middleware_native.py:561` AuthorizationMiddleware._claim_scopes
- [ ] `middleware/middleware_native.py:570` AuthorizationMiddleware._evaluate
- [ ] `middleware/middleware_native.py:585` AuthorizationMiddleware._forbidden
- [ ] `middleware/middleware_native.py:592` async AuthorizationMiddleware.process

### `middleware/middleware_observability.py`

- [ ] `middleware/middleware_observability.py:41` _BaseObservabilityMiddleware._new_request_id
- [ ] `middleware/middleware_observability.py:67` PrometheusMetricsMiddleware.process
- [ ] `middleware/middleware_observability.py:75` async _wrap
- [ ] `middleware/middleware_observability.py:83` PrometheusMetricsMiddleware._record
- [ ] `middleware/middleware_observability.py:89` PrometheusMetricsMiddleware._serve_metrics
- [ ] `middleware/middleware_observability.py:125` TracingMiddleware.process
- [ ] `middleware/middleware_observability.py:135` async _wrap
- [ ] `middleware/middleware_observability.py:167` JsonLoggingMiddleware.process
- [ ] `middleware/middleware_observability.py:176` _emit
- [ ] `middleware/middleware_observability.py:190` async _wrap
- [ ] `middleware/middleware_observability.py:221` HealthCheckMiddleware.process
- [ ] `middleware/middleware_observability.py:230` HealthCheckMiddleware._respond

### `middleware/payload_encryption.py`

- [x] `middleware/payload_encryption.py:47` KeyResolver.resolve
- [ ] `middleware/payload_encryption.py:57` CallbackKeyResolver.resolve
- [ ] `middleware/payload_encryption.py:127` async PayloadEncryptionMiddleware.process
- [ ] `middleware/payload_encryption.py:173` PayloadEncryptionMiddleware._is_excluded
- [ ] `middleware/payload_encryption.py:180` PayloadEncryptionMiddleware._decode_body
- [x] `middleware/payload_encryption.py:189` PayloadEncryptionMiddleware._decrypt_request_body
- [x] `middleware/payload_encryption.py:214` PayloadEncryptionMiddleware._encrypt_response_body
- [ ] `middleware/payload_encryption.py:245` PayloadEncryptionMiddleware._envelope
- [ ] `middleware/payload_encryption.py:253` PayloadEncryptionMiddleware._unauthorized_response
- [ ] `middleware/payload_encryption.py:264` PayloadEncryptionMiddleware._bad_request_response
- [ ] `middleware/payload_encryption.py:275` PayloadEncryptionMiddleware._internal_error

### `middleware/payload_sanitization.py`

- [ ] `middleware/payload_sanitization.py:64` PayloadSanitizationMiddleware._should_run
- [ ] `middleware/payload_sanitization.py:67` PayloadSanitizationMiddleware._handle_string
- [x] `middleware/payload_sanitization.py:79` PayloadSanitizationMiddleware._walk
- [ ] `middleware/payload_sanitization.py:107` PayloadSanitizationMiddleware._process_json_body
- [ ] `middleware/payload_sanitization.py:111` PayloadSanitizationMiddleware._coerce_body
- [ ] `middleware/payload_sanitization.py:125` PayloadSanitizationMiddleware._dump
- [ ] `middleware/payload_sanitization.py:128` async PayloadSanitizationMiddleware.process

### `middleware/pii_redaction.py`

- [ ] `middleware/pii_redaction.py:21` _json_body
- [x] `middleware/pii_redaction.py:35` _path_matches
- [ ] `middleware/pii_redaction.py:45` _strip_separators
- [ ] `middleware/pii_redaction.py:108` PIIRedactionMiddleware._is_allowed
- [ ] `middleware/pii_redaction.py:118` PIIRedactionMiddleware._looks_like_pii
- [ ] `middleware/pii_redaction.py:127` PIIRedactionMiddleware._redact
- [ ] `middleware/pii_redaction.py:143` async PIIRedactionMiddleware.process

### `middleware/rate_limit.py`

- [ ] `middleware/rate_limit.py:53` RateLimitMiddleware._key
- [ ] `middleware/rate_limit.py:67` async RateLimitMiddleware.process
- [x] `middleware/rate_limit.py:88` RateLimitMiddleware.check_batch
- [x] `middleware/rate_limit.py:95` RateLimitMiddleware._check_pure

### `middleware/request_context.py`

- [ ] `middleware/request_context.py:69` async RequestContextMiddleware.process
- [ ] `middleware/request_context.py:100` RequestContextMiddleware._read_reference_urn
- [ ] `middleware/request_context.py:112` RequestContextMiddleware._bad_reference_response

### `middleware/request_id.py`

- [ ] `middleware/request_id.py:26` async RequestIdMiddleware.process

### `middleware/request_validation.py`

- [x] `middleware/request_validation.py:21` IValidationRule.is_excluded
- [x] `middleware/request_validation.py:25` async IValidationRule.validate_request
- [x] `middleware/request_validation.py:29` async IValidationRule.sanitize_response
- [ ] `middleware/request_validation.py:55` RequestValidationMiddleware.builder
- [ ] `middleware/request_validation.py:58` RequestValidationMiddleware.register
- [ ] `middleware/request_validation.py:65` RequestValidationMiddleware.register_rule
- [ ] `middleware/request_validation.py:68` async RequestValidationMiddleware.process
- [x] `middleware/request_validation.py:94` RequestValidationMiddleware.label
- [ ] `middleware/request_validation.py:105` RequestValidationMiddlewareBuilder.with_rule
- [ ] `middleware/request_validation.py:109` RequestValidationMiddlewareBuilder.with_rules
- [ ] `middleware/request_validation.py:113` RequestValidationMiddlewareBuilder.build
- [x] `middleware/request_validation.py:117` RequestValidationMiddlewareBuilder.label

### `middleware/security.py`

- [ ] `middleware/security.py:48` async HSTSMiddleware.process

### `middleware/security_headers.py`

- [ ] `middleware/security_headers.py:65` async SecurityHeadersMiddleware.process

### `middleware/security_rules.py`

- [ ] `middleware/security_rules.py:29` _json_body
- [ ] `middleware/security_rules.py:43` _walk_strings
- [ ] `middleware/security_rules.py:56` _strip_separators
- [ ] `middleware/security_rules.py:71` _BaseRule.is_excluded
- [x] `middleware/security_rules.py:82` _BaseRule._should_abort_dict
- [ ] `middleware/security_rules.py:104` SanitizeXssRule._contains_malicious
- [ ] `middleware/security_rules.py:107` async SanitizeXssRule.validate_request
- [ ] `middleware/security_rules.py:135` async SanitizeXssRule.sanitize_response
- [ ] `middleware/security_rules.py:160` SanitizePiiRule._looks_like_pii
- [ ] `middleware/security_rules.py:168` SanitizePiiRule._walk
- [ ] `middleware/security_rules.py:184` async SanitizePiiRule.validate_request
- [ ] `middleware/security_rules.py:187` async SanitizePiiRule.sanitize_response
- [ ] `middleware/security_rules.py:224` ApiKeyLeakRule._value_is_secret
- [ ] `middleware/security_rules.py:232` ApiKeyLeakRule._key_is_secret
- [ ] `middleware/security_rules.py:235` ApiKeyLeakRule._is_allowed
- [ ] `middleware/security_rules.py:243` ApiKeyLeakRule._walk
- [ ] `middleware/security_rules.py:262` async ApiKeyLeakRule.validate_request
- [ ] `middleware/security_rules.py:265` async ApiKeyLeakRule.sanitize_response

### `middleware/sessions.py`

- [ ] `middleware/sessions.py:33` async SessionMiddleware.process
- [ ] `middleware/sessions.py:69` SessionMiddleware._load_session
- [ ] `middleware/sessions.py:82` SessionMiddleware._sign
- [ ] `middleware/sessions.py:94` SessionMiddleware._verify

### `middleware/throttling.py`

- [x] `middleware/throttling.py:19` BaseThrottle.check_many
- [x] `middleware/throttling.py:23` BaseThrottle.parse_rate
- [x] `middleware/throttling.py:35` BaseThrottle.get_ident
- [x] `middleware/throttling.py:39` BaseThrottle.allow_request
- [x] `middleware/throttling.py:57` BaseThrottle.wait
- [ ] `middleware/throttling.py:76` UserRateThrottle.get_ident
- [ ] `middleware/throttling.py:98` async ThrottleMiddleware.process

### `middleware/timeout.py`

- [ ] `middleware/timeout.py:22` async TimeoutMiddleware.process

### `middleware/tracing.py`

- [ ] `middleware/tracing.py:38` TraceparentMiddleware._default_generate
- [ ] `middleware/tracing.py:43` async TraceparentMiddleware.process
- [ ] `middleware/tracing.py:59` TraceparentMiddleware._read_header
- [x] `middleware/tracing.py:68` TraceparentMiddleware.label

### `middleware/trailing_slash.py`

- [ ] `middleware/trailing_slash.py:25` async TrailingSlashMiddleware.process

### `middleware/trusted_host.py`

- [ ] `middleware/trusted_host.py:23` async TrustedHostMiddleware.process

### `native/__init__.py`

- [x] `native/__init__.py:69` NativeHandlers.serve_static
- [x] `native/__init__.py:111` NativeHandlers.health
- [x] `native/__init__.py:146` NativeHandlers.openapi
- [x] `native/__init__.py:169` NativeHandlers.redirect

### `native/_compat.py`

- [x] `native/_compat.py:18` get_header
- [x] `native/_compat.py:29` get_request_header
- [x] `native/_compat.py:33` json_error_response
- [x] `native/_compat.py:41` parse_cookies
- [x] `native/_compat.py:54` parse_request_cookies
- [x] `native/_compat.py:59` client_ip
- [x] `native/_compat.py:71` apply_compressed_headers

### `native/abstraction.py`

- [x] `native/abstraction.py:25` ICoreRouter.add_route

### `native/asgi.py`

- [x] `native/asgi.py:48` ASGIAdapter._build
- [x] `native/asgi.py:122` async _mount_handler
- [x] `native/asgi.py:147` ASGIAdapter._apply_middleware
- [x] `native/asgi.py:167` async ASGIAdapter._handle_http
- [x] `native/asgi.py:282` async ASGIAdapter._dispatch_handler
- [x] `native/asgi.py:380` async ASGIAdapter._handle_websocket
- [x] `native/asgi.py:401` async ASGIAdapter._handle_lifespan
- [x] `native/asgi.py:462` async ASGIWebSocket.accept
- [x] `native/asgi.py:469` async ASGIWebSocket._ensure_accepted
- [x] `native/asgi.py:482` async ASGIWebSocket.receive_text
- [x] `native/asgi.py:496` async ASGIWebSocket.receive_bytes
- [x] `native/asgi.py:509` async ASGIWebSocket.receive_json
- [x] `native/asgi.py:518` async ASGIWebSocket.send_text
- [x] `native/asgi.py:521` async ASGIWebSocket.send_bytes
- [x] `native/asgi.py:524` async ASGIWebSocket.send_json
- [x] `native/asgi.py:533` async ASGIWebSocket.close

### `native/health.py`

- [x] `native/health.py:21` health

### `native/openapi_spec.py`

- [x] `native/openapi_spec.py:16` openapi

### `native/raw.py`

- [x] `native/raw.py:37` raw_response
- [x] `native/raw.py:71` raw_json
- [x] `native/raw.py:81` raw_text
- [x] `native/raw.py:93` raw_html

### `native/redirects.py`

- [x] `native/redirects.py:16` redirect

### `native/serverless.py`

- [x] `native/serverless.py:39` ServerlessAdapter._asgi_scope
- [x] `native/serverless.py:63` async ServerlessAdapter._run_asgi
- [x] `native/serverless.py:70` async receive
- [x] `native/serverless.py:77` async send

### `native/static_files.py`

- [x] `native/static_files.py:38` _build_headers
- [x] `native/static_files.py:50` _should_exclude
- [x] `native/static_files.py:62` serve_static

### `native/worker_manager.py`

- [x] `native/worker_manager.py:16` SharedState.set_str
- [x] `native/worker_manager.py:19` SharedState.set_int
- [x] `native/worker_manager.py:22` SharedState.get
- [x] `native/worker_manager.py:25` SharedState.contains
- [x] `native/worker_manager.py:28` SharedState.increment
- [x] `native/worker_manager.py:43` WorkerManager.background_process
- [x] `native/worker_manager.py:47` WorkerManager.custom_process

### `observability/abstraction.py`

- [x] `observability/abstraction.py:16` IObservability.record_metric

### `observability/debugtoolbar.py`

- [x] `observability/debugtoolbar.py:31` DebugToolbarMiddleware._should_show
- [x] `observability/debugtoolbar.py:40` async DebugToolbarMiddleware.process
- [x] `observability/debugtoolbar.py:81` DebugToolbarMiddleware._record_query
- [x] `observability/debugtoolbar.py:84` DebugToolbarMiddleware._render_panel

### `observability/health.py`

- [x] `observability/health.py:14` HealthCheck.add_check
- [x] `observability/health.py:18` HealthCheck.liveness
- [x] `observability/health.py:21` decorator
- [x] `observability/health.py:27` HealthCheck.readiness
- [x] `observability/health.py:30` decorator
- [x] `observability/health.py:36` async HealthCheck._run_checks
- [x] `observability/health.py:61` async HealthCheck.check_liveness
- [x] `observability/health.py:68` async HealthCheck.check_readiness
- [x] `observability/health.py:72` async HealthCheck.check_all
- [x] `observability/health.py:76` HealthCheck.register_routes
- [x] `observability/health.py:83` async liveness_handler
- [x] `observability/health.py:91` async readiness_handler

### `observability/metrics.py`

- [x] `observability/metrics.py:70` Counter.inc
- [x] `observability/metrics.py:81` Counter.collect
- [x] `observability/metrics.py:96` Counter._format_labels
- [x] `observability/metrics.py:126` Gauge.set
- [x] `observability/metrics.py:133` Gauge.inc
- [x] `observability/metrics.py:140` Gauge.dec
- [x] `observability/metrics.py:147` Gauge.collect
- [x] `observability/metrics.py:190` Histogram.observe
- [x] `observability/metrics.py:208` Histogram.time
- [x] `observability/metrics.py:211` Histogram.collect
- [x] `observability/metrics.py:232` Histogram._format_labels
- [x] `observability/metrics.py:240` Histogram._format_bucket_labels
- [x] `observability/metrics.py:284` MetricsRegistry.counter
- [x] `observability/metrics.py:294` MetricsRegistry.histogram
- [x] `observability/metrics.py:305` MetricsRegistry.gauge
- [x] `observability/metrics.py:310` MetricsRegistry.collect
- [x] `observability/metrics.py:318` MetricsRegistry.register_routes
- [x] `observability/metrics.py:322` metrics_endpoint
- [x] `observability/metrics.py:351` async MetricsMiddleware.process
- [x] `observability/metrics.py:370` _format_value

### `observability/otel.py`

- [x] `observability/otel.py:42` async OpenTelemetryMiddleware.process
- [x] `observability/otel.py:70` configure_otel
- [x] `observability/otel.py:110` set_tracer
- [x] `observability/otel.py:118` get_tracer

### `observability/sentry.py`

- [x] `observability/sentry.py:44` async SentryMiddleware.process
- [x] `observability/sentry.py:63` configure_sentry
- [x] `observability/sentry.py:93` capture_exception
- [x] `observability/sentry.py:104` async wrapper
- [x] `observability/sentry.py:118` set_user_context
- [x] `observability/sentry.py:126` set_extra_context

### `observability/structlog.py`

- [x] `observability/structlog.py:21` JSONFormatter.format
- [x] `observability/structlog.py:51` StructuredLogger._log
- [x] `observability/structlog.py:55` StructuredLogger.debug
- [x] `observability/structlog.py:58` StructuredLogger.info
- [x] `observability/structlog.py:61` StructuredLogger.warning
- [x] `observability/structlog.py:64` StructuredLogger.error
- [x] `observability/structlog.py:67` StructuredLogger.critical
- [x] `observability/structlog.py:78` async StructuredAccessLogMiddleware.process
- [x] `observability/structlog.py:98` configure_logging

### `observability/tracing.py`

- [x] `observability/tracing.py:24` Span.set_attribute
- [x] `observability/tracing.py:27` Span.set_status
- [x] `observability/tracing.py:30` Span.end
- [x] `observability/tracing.py:34` Span.duration_ms
- [x] `observability/tracing.py:38` Span.to_dict
- [x] `observability/tracing.py:56` SpanExporter.export
- [x] `observability/tracing.py:63` ConsoleSpanExporter.export
- [x] `observability/tracing.py:86` OTelSpanExporter.export
- [x] `observability/tracing.py:101` configure_tracing
- [x] `observability/tracing.py:125` async TracingMiddleware.process
- [x] `observability/tracing.py:175` TracingMiddleware._parse_traceparent

### `openapi/asyncapi.py`

- [x] `openapi/asyncapi.py:13` generate_asyncapi
- [x] `openapi/asyncapi.py:97` build_asyncapi_html

### `openapi/openapi.py`

- [x] `openapi/openapi.py:10` generate_openapi
- [x] `openapi/openapi.py:88` _build_operation
- [x] `openapi/openapi.py:304` _collect_security_requirement
- [x] `openapi/openapi.py:317` _extract_path_params
- [x] `openapi/openapi.py:325` _type_to_schema
- [x] `openapi/openapi.py:339` _model_to_ref
- [x] `openapi/openapi.py:360` _is_request_type
- [x] `openapi/openapi.py:369` _is_body_model
- [x] `openapi/openapi.py:380` _is_internal_type
- [x] `openapi/openapi.py:393` _is_file_type
- [x] `openapi/openapi.py:406` _is_form_type
- [x] `openapi/openapi.py:415` build_docs_html
- [x] `openapi/openapi.py:449` build_redoc_html
- [x] `openapi/openapi.py:466` build_health_html
- [x] `openapi/openapi.py:491` build_admin_html
- [x] `openapi/openapi.py:513` _brand_mark
- [x] `openapi/openapi.py:535` build_server_html
- [x] `openapi/openapi.py:673` _powered_by
- [x] `openapi/openapi.py:688` _powered_by_rivex
- [x] `openapi/openapi.py:703` _fallback_docs_html
- [x] `openapi/openapi.py:1284` _fallback_redoc_html
- [x] `openapi/openapi.py:1296` _fallback_health_html
- [x] `openapi/openapi.py:1356` _fallback_admin_html

### `openapi/scalar.py`

- [x] `openapi/scalar.py:26` render_scalar_html
- [x] `openapi/scalar.py:64` mount_scalar
- [x] `openapi/scalar.py:93` _scalar_page

### `protocols/feeds.py`

- [ ] `protocols/feeds.py:34` Sitemap.add_url
- [ ] `protocols/feeds.py:57` Sitemap.render
- [ ] `protocols/feeds.py:99` SitemapIndex.add_sitemap
- [ ] `protocols/feeds.py:108` SitemapIndex.render
- [ ] `protocols/feeds.py:146` RssFeed.add_item
- [ ] `protocols/feeds.py:170` RssFeed._format_date
- [ ] `protocols/feeds.py:177` RssFeed.render
- [ ] `protocols/feeds.py:230` AtomFeed.add_item
- [ ] `protocols/feeds.py:260` AtomFeed.render

### `protocols/graphql.py`

- [ ] `protocols/graphql.py:39` GraphQLMiddleware.schema
- [ ] `protocols/graphql.py:43` GraphQLMiddleware.schema
- [ ] `protocols/graphql.py:46` async GraphQLMiddleware.process
- [ ] `protocols/graphql.py:101` GraphQLMiddleware._graphiql_html
- [x] `protocols/graphql.py:127` graphql_query
- [ ] `protocols/graphql.py:129` decorator
- [x] `protocols/graphql.py:136` graphql_mutation
- [ ] `protocols/graphql.py:138` decorator

### `protocols/grpc.py`

- [ ] `protocols/grpc.py:34` GRPCServer.add_service
- [ ] `protocols/grpc.py:37` GRPCServer.add_servicer
- [ ] `protocols/grpc.py:40` GRPCServer.start
- [ ] `protocols/grpc.py:71` GRPCServer._add_servicer_from_impl
- [ ] `protocols/grpc.py:83` GRPCServer.stop
- [ ] `protocols/grpc.py:92` GRPCServer.run_in_thread
- [ ] `protocols/grpc.py:93` target
- [ ] `protocols/grpc.py:101` GRPCServer.wait_for_termination
- [ ] `protocols/grpc.py:120` async GRPCClient._get_channel
- [ ] `protocols/grpc.py:133` async GRPCClient.call
- [ ] `protocols/grpc.py:141` async GRPCClient.close

### `protocols/grpc_web.py`

- [ ] `protocols/grpc_web.py:34` GRPCWebMiddleware.add_service
- [ ] `protocols/grpc_web.py:37` GRPCWebMiddleware._parse_grpc_request
- [ ] `protocols/grpc_web.py:42` GRPCWebMiddleware._encode_grpc_response
- [ ] `protocols/grpc_web.py:49` async GRPCWebMiddleware.process
- [ ] `protocols/grpc_web.py:116` async GRPCWebMiddleware._call_grpc
- [ ] `protocols/grpc_web.py:144` GRPCWebMiddleware._find_stub_class
- [ ] `protocols/grpc_web.py:156` GRPCWebMiddleware._find_request_class
- [ ] `protocols/grpc_web.py:185` GRPCWebServer.add_service

### `protocols/http3.py`

- [ ] `protocols/http3.py:46` QUICServer._create_ssl_context
- [ ] `protocols/http3.py:52` async QUICServer._handle_quic
- [ ] `protocols/http3.py:69` async handler_func
- [ ] `protocols/http3.py:90` QUICServer.start
- [ ] `protocols/http3.py:100` target
- [ ] `protocols/http3.py:108` QUICServer.stop
- [ ] `protocols/http3.py:127` async QUICClient.get
- [ ] `protocols/http3.py:149` async QUICClient.post

### `protocols/jsonrpc.py`

- [x] `protocols/jsonrpc.py:36` JSONRPCMiddleware.method
- [ ] `protocols/jsonrpc.py:44` decorator
- [ ] `protocols/jsonrpc.py:50` JSONRPCMiddleware.before_request
- [ ] `protocols/jsonrpc.py:54` JSONRPCMiddleware.after_request
- [ ] `protocols/jsonrpc.py:58` JSONRPCMiddleware._make_error
- [ ] `protocols/jsonrpc.py:65` JSONRPCMiddleware._make_success
- [ ] `protocols/jsonrpc.py:68` async JSONRPCMiddleware.process
- [ ] `protocols/jsonrpc.py:170` XMLRPCMiddleware.method
- [ ] `protocols/jsonrpc.py:171` decorator
- [ ] `protocols/jsonrpc.py:177` XMLRPCMiddleware._parse_xmlrpc_request
- [ ] `protocols/jsonrpc.py:189` XMLRPCMiddleware._xml_to_python
- [ ] `protocols/jsonrpc.py:218` XMLRPCMiddleware._python_to_xml
- [ ] `protocols/jsonrpc.py:237` async XMLRPCMiddleware.process

### `protocols/mqtt.py`

- [ ] `protocols/mqtt.py:53` async MQTTBridge.connect
- [ ] `protocols/mqtt.py:76` MQTTBridge._on_connect
- [ ] `protocols/mqtt.py:82` MQTTBridge._on_message
- [ ] `protocols/mqtt.py:100` MQTTBridge._topic_matches
- [ ] `protocols/mqtt.py:114` MQTTBridge._forward_to_ws_clients
- [x] `protocols/mqtt.py:126` MQTTBridge.on_message
- [ ] `protocols/mqtt.py:131` decorator
- [ ] `protocols/mqtt.py:136` async MQTTBridge.publish
- [ ] `protocols/mqtt.py:144` async MQTTBridge.subscribe
- [ ] `protocols/mqtt.py:150` MQTTBridge.register_ws_client
- [ ] `protocols/mqtt.py:154` MQTTBridge.unregister_ws_client
- [ ] `protocols/mqtt.py:158` async MQTTBridge.handle_websocket
- [ ] `protocols/mqtt.py:177` async MQTTBridge.disconnect

### `protocols/rawsocket.py`

- [ ] `protocols/rawsocket.py:56` RawTCPServer.on_connect
- [ ] `protocols/rawsocket.py:60` RawTCPServer.on_connect
- [ ] `protocols/rawsocket.py:65` RawTCPServer.on_disconnect
- [ ] `protocols/rawsocket.py:69` RawTCPServer.on_disconnect
- [ ] `protocols/rawsocket.py:72` async RawTCPServer._handle_client
- [ ] `protocols/rawsocket.py:88` async RawTCPServer._run_server
- [ ] `protocols/rawsocket.py:109` RawTCPServer.start
- [ ] `protocols/rawsocket.py:113` target
- [ ] `protocols/rawsocket.py:121` RawTCPServer.stop
- [ ] `protocols/rawsocket.py:153` UnixSocketServer.on_connect
- [ ] `protocols/rawsocket.py:157` UnixSocketServer.on_connect
- [ ] `protocols/rawsocket.py:160` async UnixSocketServer._handle_client
- [ ] `protocols/rawsocket.py:173` async UnixSocketServer._run_server
- [ ] `protocols/rawsocket.py:191` UnixSocketServer.start
- [ ] `protocols/rawsocket.py:195` target
- [ ] `protocols/rawsocket.py:203` UnixSocketServer.stop
- [ ] `protocols/rawsocket.py:235` UDPBroadcastServer.on_message
- [ ] `protocols/rawsocket.py:239` UDPBroadcastServer.on_message
- [ ] `protocols/rawsocket.py:246` UDPBroadcastServer._UDPProtocol.datagram_received
- [ ] `protocols/rawsocket.py:254` UDPBroadcastServer._UDPProtocol.error_received
- [ ] `protocols/rawsocket.py:257` async UDPBroadcastServer.send
- [ ] `protocols/rawsocket.py:261` async UDPBroadcastServer._run_server
- [ ] `protocols/rawsocket.py:271` UDPBroadcastServer.start
- [ ] `protocols/rawsocket.py:275` target
- [ ] `protocols/rawsocket.py:284` UDPBroadcastServer.stop

### `protocols/socketio.py`

- [x] `protocols/socketio.py:46` SocketIOServer.on
- [ ] `protocols/socketio.py:55` decorator
- [ ] `protocols/socketio.py:63` SocketIOServer.use
- [ ] `protocols/socketio.py:66` async SocketIOServer.create_session
- [ ] `protocols/socketio.py:71` async SocketIOServer.handle_connect
- [ ] `protocols/socketio.py:79` async SocketIOServer.handle_event
- [ ] `protocols/socketio.py:86` async SocketIOServer.handle_disconnect
- [ ] `protocols/socketio.py:93` async SocketIOServer.emit
- [ ] `protocols/socketio.py:114` SocketIOServer._encode_packet
- [ ] `protocols/socketio.py:118` SocketIOServer.join_room
- [ ] `protocols/socketio.py:121` SocketIOServer.leave_room
- [ ] `protocols/socketio.py:125` SocketIOServer.sessions
- [ ] `protocols/socketio.py:128` SocketIOServer.connected_count
- [ ] `protocols/socketio.py:141` async SocketIOSession.send
- [ ] `protocols/socketio.py:144` async SocketIOSession.receive
- [ ] `protocols/socketio.py:166` async SocketIOMiddleware.process
- [ ] `protocols/socketio.py:177` async SocketIOMiddleware._handle_http_longpoll
- [ ] `protocols/socketio.py:208` async SocketIOMiddleware._handle_websocket

### `protocols/sse.py`

- [ ] `protocols/sse.py:47` SSEEvent._format

### `protocols/webhooks.py`

- [ ] `protocols/webhooks.py:16` _hmac_verify
- [ ] `protocols/webhooks.py:31` _verify_stripe
- [ ] `protocols/webhooks.py:72` _verify_github
- [ ] `protocols/webhooks.py:80` _verify_generic
- [ ] `protocols/webhooks.py:86` verify_signature

### `protocols/websocket.py`

- [ ] `protocols/websocket.py:71` async WebSocket.accept
- [ ] `protocols/websocket.py:89` async WebSocket.receive_text
- [ ] `protocols/websocket.py:95` async WebSocket.receive_bytes
- [ ] `protocols/websocket.py:101` async WebSocket.receive_json
- [ ] `protocols/websocket.py:108` async WebSocket.send_text
- [ ] `protocols/websocket.py:115` async WebSocket.send_bytes
- [ ] `protocols/websocket.py:122` async WebSocket.send_json
- [ ] `protocols/websocket.py:129` async WebSocket.close
- [ ] `protocols/websocket.py:146` async WebSocket._read_frame
- [ ] `protocols/websocket.py:151` async WebSocket._read_frame_rust
- [ ] `protocols/websocket.py:203` WebSocket._decode_payload_length
- [ ] `protocols/websocket.py:211` async WebSocket._read_frame_py
- [ ] `protocols/websocket.py:257` async WebSocket._write_frame
- [ ] `protocols/websocket.py:279` _compute_accept_key
- [ ] `protocols/websocket.py:284` is_websocket_upgrade
- [ ] `protocols/websocket.py:298` _build_pong

### `protocols/websockets.py`

- [x] `protocols/websockets.py:45` async WebSocket.receive
- [x] `protocols/websockets.py:54` async WebSocket.receive_text
- [x] `protocols/websockets.py:69` async WebSocket.receive_bytes
- [x] `protocols/websockets.py:79` async WebSocket.receive_json
- [ ] `protocols/websockets.py:88` async WebSocket.send_text
- [ ] `protocols/websockets.py:91` async WebSocket.send_bytes
- [x] `protocols/websockets.py:94` async WebSocket.send_json
- [x] `protocols/websockets.py:104` async WebSocket.close

### `protocols/webtransport.py`

- [ ] `protocols/webtransport.py:62` WebTransportServer.on_connect
- [ ] `protocols/webtransport.py:66` WebTransportServer.on_connect
- [ ] `protocols/webtransport.py:70` WebTransportServer.on_disconnect
- [ ] `protocols/webtransport.py:74` WebTransportServer.on_disconnect
- [ ] `protocols/webtransport.py:78` WebTransportServer.on_datagram
- [ ] `protocols/webtransport.py:82` WebTransportServer.on_datagram
- [ ] `protocols/webtransport.py:86` WebTransportServer.on_stream
- [ ] `protocols/webtransport.py:90` WebTransportServer.on_stream
- [ ] `protocols/webtransport.py:93` async WebTransportServer._handle_session
- [ ] `protocols/webtransport.py:114` async WebTransportServer._run_server
- [ ] `protocols/webtransport.py:141` async session_handler
- [ ] `protocols/webtransport.py:160` WebTransportServer.start
- [ ] `protocols/webtransport.py:164` target
- [ ] `protocols/webtransport.py:172` WebTransportServer.stop
- [ ] `protocols/webtransport.py:179` WebTransportServer.sessions
- [ ] `protocols/webtransport.py:182` WebTransportServer.broadcast_datagram
- [ ] `protocols/webtransport.py:200` async WebTransportSession.send_datagram
- [ ] `protocols/webtransport.py:206` async WebTransportSession.send_stream
- [ ] `protocols/webtransport.py:209` async WebTransportSession.receive_datagram
- [ ] `protocols/webtransport.py:213` async WebTransportSession.close
- [ ] `protocols/webtransport.py:222` WebTransportSession.connected
- [ ] `protocols/webtransport.py:238` async WebTransportClient.connect

### `protocols/ws.py`

- [ ] `protocols/ws.py:16` async ConnectionManager.connect
- [ ] `protocols/ws.py:23` ConnectionManager.disconnect
- [ ] `protocols/ws.py:30` async ConnectionManager.broadcast
- [ ] `protocols/ws.py:37` async ConnectionManager.broadcast_json
- [ ] `protocols/ws.py:40` async ConnectionManager.send_to_room
- [ ] `protocols/ws.py:47` async ConnectionManager.send_json_to_room
- [ ] `protocols/ws.py:50` ConnectionManager.join_room
- [ ] `protocols/ws.py:53` ConnectionManager.leave_room
- [ ] `protocols/ws.py:59` ConnectionManager.active_connections
- [ ] `protocols/ws.py:62` ConnectionManager.rooms

### `serialization/_bodies.py`

- [x] `serialization/_bodies.py:66` _coerce_str
- [x] `serialization/_bodies.py:70` _coerce_int
- [x] `serialization/_bodies.py:77` _coerce_float
- [x] `serialization/_bodies.py:84` _coerce_bool
- [x] `serialization/_bodies.py:88` _coerce_passthrough
- [x] `serialization/_bodies.py:150` _pydantic_base_model
- [x] `serialization/_bodies.py:158` _marshmallow_schema_base
- [x] `serialization/_bodies.py:167` _msgspec_struct_base
- [x] `serialization/_bodies.py:176` _construct_struct_base
- [x] `serialization/_bodies.py:185` _construct_container_base
- [x] `serialization/_bodies.py:194` _is_attrs_class
- [x] `serialization/_bodies.py:210` _is_dataclass
- [x] `serialization/_bodies.py:222` _has_typeguard
- [x] `serialization/_bodies.py:249` _detect_pydantic
- [x] `serialization/_bodies.py:256` _detect_marshmallow
- [x] `serialization/_bodies.py:263` _detect_rivex_schema
- [x] `serialization/_bodies.py:278` _detect_msgspec
- [x] `serialization/_bodies.py:285` _detect_construct
- [x] `serialization/_bodies.py:295` _detect_attrs
- [x] `serialization/_bodies.py:301` _detect_dataclass
- [x] `serialization/_bodies.py:353` _classify_via_cache
- [x] `serialization/_bodies.py:367` body_schema
- [x] `serialization/_bodies.py:394` is_body_model
- [x] `serialization/_bodies.py:418` _coerce_field_by_type
- [x] `serialization/_bodies.py:439` _coerce_form_attrs
- [x] `serialization/_bodies.py:471` _coerce_form_dataclass
- [x] `serialization/_bodies.py:488` _coerce_form_dict
- [x] `serialization/_bodies.py:493` _coerce_form_msgspec
- [x] `serialization/_bodies.py:507` _coerce_form_pydantic
- [x] `serialization/_bodies.py:512` _coerce_form_marshmallow
- [x] `serialization/_bodies.py:517` _coerce_form_construct
- [x] `serialization/_bodies.py:533` _coerce_form_typeguard
- [x] `serialization/_bodies.py:567` coerce_form_data
- [x] `serialization/_bodies.py:594` _decode_body
- [x] `serialization/_bodies.py:629` _parse_json_payload
- [x] `serialization/_bodies.py:647` _coerce_body_pydantic
- [x] `serialization/_bodies.py:654` _coerce_body_marshmallow
- [x] `serialization/_bodies.py:659` _coerce_body_dataclass
- [x] `serialization/_bodies.py:664` _coerce_body_attrs
- [x] `serialization/_bodies.py:673` _coerce_body_msgspec
- [x] `serialization/_bodies.py:680` _coerce_body_construct
- [x] `serialization/_bodies.py:697` _coerce_body_typeguard
- [x] `serialization/_bodies.py:706` _coerce_body_dict
- [x] `serialization/_bodies.py:715` _coerce_body_custom
- [x] `serialization/_bodies.py:753` coerce_body
- [x] `serialization/_bodies.py:813` register_body_schema
- [x] `serialization/_bodies.py:849` body_schema_extended

### `serialization/_json.py`

- [x] `serialization/_json.py:22` dumps
- [x] `serialization/_json.py:31` loads

### `serialization/abstraction.py`

- [x] `serialization/abstraction.py:16` ISerializer.serialize
- [x] `serialization/abstraction.py:21` ISerializer.deserialize

### `serialization/encoders.py`

- [x] `serialization/encoders.py:12` jsonable_encoder

### `serialization/gen.py`

- [x] `serialization/gen.py:119` F.fmt
- [x] `serialization/gen.py:127` F.repeat
- [x] `serialization/gen.py:135` F.mul
- [x] `serialization/gen.py:143` F.add
- [x] `serialization/gen.py:151` F.sub
- [x] `serialization/gen.py:159` F.mod_
- [x] `serialization/gen.py:167` F.range
- [x] `serialization/gen.py:175` F.cycle
- [x] `serialization/gen.py:189` F.nested
- [x] `serialization/gen.py:212` gen.list
- [x] `serialization/gen.py:224` gen.object
- [x] `serialization/gen.py:239` gen.wrap
- [x] `serialization/gen.py:258` gen.array
- [x] `serialization/gen.py:279` gen.dict
- [x] `serialization/gen.py:295` gen.set
- [x] `serialization/gen.py:306` gen.frozenset
- [x] `serialization/gen.py:317` gen.tuple
- [x] `serialization/gen.py:328` gen.pylist
- [x] `serialization/gen.py:345` gen.csv
- [x] `serialization/gen.py:360` gen.ndjson

### `serialization/schema.py`

- [x] `serialization/schema.py:128` _is_classvar
- [x] `serialization/schema.py:230` Field._apply_numeric
- [x] `serialization/schema.py:239` Field._apply_decimal
- [x] `serialization/schema.py:247` Field._apply_string
- [x] `serialization/schema.py:256` Field._apply_collection
- [x] `serialization/schema.py:263` Field._json_schema_meta
- [x] `serialization/schema.py:279` _is_pydantic_json
- [x] `serialization/schema.py:285` _try_pydantic_native_schema
- [x] `serialization/schema.py:301` _takes_info
- [x] `serialization/schema.py:310` _apply_constraints
- [x] `serialization/schema.py:327` _literal_value
- [x] `serialization/schema.py:341` _extract_discriminator_tag
- [x] `serialization/schema.py:360` _annotation_to_core_schema
- [x] `serialization/schema.py:498` _to_path
- [x] `serialization/schema.py:514` _to_ip
- [x] `serialization/schema.py:609` _apply_field_constraints
- [x] `serialization/schema.py:623` _model_field_kwargs
- [x] `serialization/schema.py:680` _unwrap_callable
- [x] `serialization/schema.py:685` _collect_decorations
- [x] `serialization/schema.py:759` _wrap_with_field_serializer
- [x] `serialization/schema.py:788` _wrap_with_field_validator
- [x] `serialization/schema.py:800` _wrap_with_model_validator
- [x] `serialization/schema.py:954` _run_post_init
- [x] `serialization/schema.py:996` Schema.model_validate_json
- [x] `serialization/schema.py:1002` Schema.model_validate
- [x] `serialization/schema.py:1007` Schema.model_dump
- [x] `serialization/schema.py:1034` Schema.model_dump_json
- [x] `serialization/schema.py:1061` Schema.model_copy
- [x] `serialization/schema.py:1074` Schema.model_construct
- [x] `serialization/schema.py:1102` Schema.model_fields_set
- [x] `serialization/schema.py:1107` Schema.model_extra
- [x] `serialization/schema.py:1112` Schema.model_json_schema

### `serialization/serialization.py`

- [x] `serialization/serialization.py:8` _default_serializer
- [x] `serialization/serialization.py:38` serialize
- [x] `serialization/serialization.py:45` deserialize

### `serialization/serializers.py`

- [x] `serialization/serializers.py:33` Field.to_internal_value
- [x] `serialization/serializers.py:46` Field.to_representation
- [x] `serialization/serializers.py:69` Serializer._build_fields
- [x] `serialization/serializers.py:76` Serializer.fields
- [x] `serialization/serializers.py:80` Serializer.errors
- [x] `serialization/serializers.py:84` Serializer.validated_data
- [x] `serialization/serializers.py:87` Serializer.is_valid
- [x] `serialization/serializers.py:109` Serializer.to_representation
- [x] `serialization/serializers.py:122` Serializer.data
- [x] `serialization/serializers.py:131` ModelSerializer._build_fields
- [x] `serialization/serializers.py:147` ListSerializer.is_valid
- [x] `serialization/serializers.py:160` ListSerializer.to_representation

### `testing/abstraction.py`

- [x] `testing/abstraction.py:16` ITestClient.get
- [x] `testing/abstraction.py:21` ITestClient.post

### `testing/testing.py`

- [x] `testing/testing.py:21` TestResponse.text
- [x] `testing/testing.py:24` TestResponse.json
- [x] `testing/testing.py:48` TestClient.get
- [x] `testing/testing.py:51` TestClient.post
- [x] `testing/testing.py:54` TestClient.put
- [x] `testing/testing.py:57` TestClient.patch
- [x] `testing/testing.py:60` TestClient.delete
- [x] `testing/testing.py:63` TestClient.websocket_connect
- [x] `testing/testing.py:66` TestClient.request
- [x] `testing/testing.py:85` async _dispatch
- [x] `testing/testing.py:118` async _wrap
- [x] `testing/testing.py:154` TestClient._get_sync_app
- [x] `testing/testing.py:189` async _wrap
- [x] `testing/testing.py:211` async _mount_handler
- [x] `testing/testing.py:238` async _k8s_handler
- [x] `testing/testing.py:252` TestClient._register_test_asyncapi
- [x] `testing/testing.py:264` async handler
- [x] `testing/testing.py:279` async docs_handler
- [x] `testing/testing.py:288` TestClient._get_mw_instances
- [x] `testing/testing.py:298` TestClient._get_route_mw_instances
- [x] `testing/testing.py:313` TestClient._build_request
- [x] `testing/testing.py:354` TestClient._to_response
- [x] `testing/testing.py:371` TestClient._collect_stream
- [x] `testing/testing.py:375` async _collect
- [x] `testing/testing.py:418` _TestWebSocket.send_text
- [x] `testing/testing.py:421` _TestWebSocket.send_json
- [x] `testing/testing.py:424` _TestWebSocket.receive_text
- [x] `testing/testing.py:430` _TestWebSocket.receive_json
- [x] `testing/testing.py:435` json_module_dumps

### `testing/testing_fixtures.py`

- [x] `testing/testing_fixtures.py:41` app
- [x] `testing/testing_fixtures.py:57` client
- [x] `testing/testing_fixtures.py:70` db
- [x] `testing/testing_fixtures.py:93` http_mock
- [x] `testing/testing_fixtures.py:122` redis_mock
- [x] `testing/testing_fixtures.py:150` s3_mock
- [x] `testing/testing_fixtures.py:178` time_mock

### `utilities/_response_compat.py`

- [x] `utilities/_response_compat.py:19` ResponseUtility.mint_urn
- [x] `utilities/_response_compat.py:25` ResponseUtility.mint_reference_urn
- [x] `utilities/_response_compat.py:32` ResponseUtility.iso8601_now

### `utilities/abstraction.py`

- [x] `utilities/abstraction.py:15` IUtility.label

### `utilities/crypto/__init__.py`

- [x] `utilities/crypto/__init__.py:21` CryptoUtility.label

### `utilities/crypto/abstraction.py`

- [x] `utilities/crypto/abstraction.py:15` ICryptoUtility.label

### `utilities/crypto/asymmetric.py`

- [x] `utilities/crypto/asymmetric.py:21` AsymmetricCryptoUtility.generate_ed25519_keypair
- [x] `utilities/crypto/asymmetric.py:53` AsymmetricCryptoUtility.ed25519_sign
- [x] `utilities/crypto/asymmetric.py:73` AsymmetricCryptoUtility.ed25519_verify
- [x] `utilities/crypto/asymmetric.py:95` AsymmetricCryptoUtility.label

### `utilities/crypto/payload.py`

- [x] `utilities/crypto/payload.py:49` PayloadCrypto.derive_system_key
- [x] `utilities/crypto/payload.py:60` PayloadCrypto.protect_fernet_key
- [x] `utilities/crypto/payload.py:68` PayloadCrypto.unprotect_fernet_key

### `utilities/crypto/symmetric.py`

- [x] `utilities/crypto/symmetric.py:27` SymmetricCryptoUtility.sha256
- [x] `utilities/crypto/symmetric.py:37` SymmetricCryptoUtility.hmac_sha256
- [x] `utilities/crypto/symmetric.py:48` SymmetricCryptoUtility.hmac_sha256_verify
- [x] `utilities/crypto/symmetric.py:60` SymmetricCryptoUtility.random_token
- [x] `utilities/crypto/symmetric.py:64` SymmetricCryptoUtility.random_bytes
- [x] `utilities/crypto/symmetric.py:68` SymmetricCryptoUtility.random_hex
- [x] `utilities/crypto/symmetric.py:72` SymmetricCryptoUtility.generate_OTP
- [x] `utilities/crypto/symmetric.py:76` SymmetricCryptoUtility.generate_fernet_key
- [x] `utilities/crypto/symmetric.py:88` SymmetricCryptoUtility.pbkdf2_derive
- [x] `utilities/crypto/symmetric.py:105` SymmetricCryptoUtility.aes_gcm_encrypt
- [x] `utilities/crypto/symmetric.py:124` SymmetricCryptoUtility.aes_gcm_decrypt
- [x] `utilities/crypto/symmetric.py:141` SymmetricCryptoUtility.fernet_encrypt
- [x] `utilities/crypto/symmetric.py:153` SymmetricCryptoUtility.fernet_decrypt
- [ ] `utilities/crypto/symmetric.py:169` SymmetricCryptoUtility._fernet_key
- [x] `utilities/crypto/symmetric.py:175` SymmetricCryptoUtility.label

### `utilities/database/abstraction.py`

- [x] `utilities/database/abstraction.py:15` IDatabaseUtility.label

### `utilities/database/mongo.py`

- [x] `utilities/database/mongo.py:31` async MongoDatabaseUtility.connect
- [x] `utilities/database/mongo.py:42` async MongoDatabaseUtility.disconnect
- [x] `utilities/database/mongo.py:48` MongoDatabaseUtility.get_collection
- [ ] `utilities/database/mongo.py:55` MongoDatabaseUtility.client
- [x] `utilities/database/mongo.py:59` MongoDatabaseUtility.label

### `utilities/database/postgres.py`

- [x] `utilities/database/postgres.py:33` async PostgresDatabaseUtility.connect
- [x] `utilities/database/postgres.py:48` async PostgresDatabaseUtility.disconnect
- [x] `utilities/database/postgres.py:54` async PostgresDatabaseUtility.fetch
- [x] `utilities/database/postgres.py:61` async PostgresDatabaseUtility.execute
- [ ] `utilities/database/postgres.py:69` PostgresDatabaseUtility.pool
- [x] `utilities/database/postgres.py:73` PostgresDatabaseUtility.label

### `utilities/env.py`

- [x] `utilities/env.py:17` EnvUtility.get
- [x] `utilities/env.py:24` EnvUtility.require
- [x] `utilities/env.py:31` EnvUtility.get_int
- [x] `utilities/env.py:43` EnvUtility.get_bytes
- [x] `utilities/env.py:60` EnvUtility.get_bool
- [x] `utilities/env.py:68` EnvUtility.label

### `utilities/hashing.py`

- [x] `utilities/hashing.py:17` HashingUtility.hash
- [x] `utilities/hashing.py:29` HashingUtility.verify
- [x] `utilities/hashing.py:34` HashingUtility.label

### `utilities/hmac.py`

- [x] `utilities/hmac.py:17` HMACUtility.generate
- [x] `utilities/hmac.py:24` HMACUtility.verify
- [x] `utilities/hmac.py:36` HMACUtility.label

### `utilities/jwt.py`

- [x] `utilities/jwt.py:41` JWTUtility.label
- [x] `utilities/jwt.py:45` JWTUtility._create_payload
- [x] `utilities/jwt.py:62` JWTUtility._encode
- [x] `utilities/jwt.py:70` JWTUtility._decode
- [x] `utilities/jwt.py:78` JWTUtility.create_access_token
- [x] `utilities/jwt.py:90` JWTUtility.create_refresh_token
- [x] `utilities/jwt.py:102` JWTUtility.decode_access_token
- [x] `utilities/jwt.py:106` JWTUtility.decode_refresh_token

### `utilities/otp/abstraction.py`

- [x] `utilities/otp/abstraction.py:51` IOTPUtility.alphabet_regex
- [x] `utilities/otp/abstraction.py:56` IOTPUtility.passphrase_regex
- [ ] `utilities/otp/abstraction.py:60` IOTPUtility._from_alphabet
- [x] `utilities/otp/abstraction.py:68` IOTPUtility.generate
- [x] `utilities/otp/abstraction.py:72` IOTPUtility.validate
- [x] `utilities/otp/abstraction.py:77` IOTPUtility.label

### `utilities/otp/alphabetic.py`

- [x] `utilities/otp/alphabetic.py:25` AlphabeticOTPUtility.generate
- [x] `utilities/otp/alphabetic.py:32` AlphabeticOTPUtility.validate
- [x] `utilities/otp/alphabetic.py:37` AlphabeticOTPUtility.label

### `utilities/otp/alphanumeric.py`

- [x] `utilities/otp/alphanumeric.py:25` AlphanumericOTPUtility.generate
- [x] `utilities/otp/alphanumeric.py:32` AlphanumericOTPUtility.validate
- [x] `utilities/otp/alphanumeric.py:37` AlphanumericOTPUtility.label

### `utilities/otp/digit.py`

- [x] `utilities/otp/digit.py:24` DigitOTPUtility.generate
- [x] `utilities/otp/digit.py:31` DigitOTPUtility.validate
- [x] `utilities/otp/digit.py:36` DigitOTPUtility.label

### `utilities/otp/hex.py`

- [x] `utilities/otp/hex.py:25` HexOTPUtility.generate
- [x] `utilities/otp/hex.py:32` HexOTPUtility.validate
- [x] `utilities/otp/hex.py:37` HexOTPUtility.label

### `utilities/otp/passphrase.py`

- [x] `utilities/otp/passphrase.py:28` PassphraseOTPUtility.generate
- [x] `utilities/otp/passphrase.py:38` PassphraseOTPUtility.validate
- [x] `utilities/otp/passphrase.py:43` PassphraseOTPUtility.label

### `utilities/regex.py`

- [x] `utilities/regex.py:18` RegexUtility.compile_patterns
- [x] `utilities/regex.py:33` RegexUtility.label

### `utilities/request/body.py`

- [x] `utilities/request/body.py:20` RequestBodyUtility.get_request_body
- [x] `utilities/request/body.py:26` RequestBodyUtility.set_request_body
- [x] `utilities/request/body.py:31` RequestBodyUtility.get_request_body_size
- [x] `utilities/request/body.py:36` RequestBodyUtility.get_request_body_text
- [x] `utilities/request/body.py:41` RequestBodyUtility.get_request_body_json

### `utilities/request/form.py`

- [x] `utilities/request/form.py:18` RequestFormUtility.get_request_form
- [x] `utilities/request/form.py:24` RequestFormUtility.set_request_form
- [x] `utilities/request/form.py:29` RequestFormUtility.get_request_form_value
- [x] `utilities/request/form.py:38` RequestFormUtility.get_request_form_values
- [x] `utilities/request/form.py:48` RequestFormUtility.get_request_form_file
- [x] `utilities/request/form.py:56` RequestFormUtility.get_request_form_files

### `utilities/request/header.py`

- [x] `utilities/request/header.py:17` RequestHeaderUtility.get_request_header
- [x] `utilities/request/header.py:27` RequestHeaderUtility.get_all_request_headers
- [x] `utilities/request/header.py:34` RequestHeaderUtility.set_request_header
- [x] `utilities/request/header.py:43` RequestHeaderUtility.add_request_header
- [x] `utilities/request/header.py:50` RequestHeaderUtility.remove_request_header
- [x] `utilities/request/header.py:60` RequestHeaderUtility.has_request_header

### `utilities/request/param.py`

- [x] `utilities/request/param.py:22` RequestParamUtility.get_path_param
- [x] `utilities/request/param.py:28` RequestParamUtility.set_path_param
- [x] `utilities/request/param.py:35` RequestParamUtility.get_path_params
- [x] `utilities/request/param.py:40` RequestParamUtility.get_query_string
- [x] `utilities/request/param.py:45` RequestParamUtility.set_query_string
- [x] `utilities/request/param.py:51` RequestParamUtility.get_query_params
- [x] `utilities/request/param.py:64` RequestParamUtility.get_query_value
- [x] `utilities/request/param.py:71` RequestParamUtility.get_cookies
- [x] `utilities/request/param.py:93` RequestParamUtility.get_cookie
- [x] `utilities/request/param.py:98` RequestParamUtility.dump_query_params_as_json

### `utilities/request/state.py`

- [x] `utilities/request/state.py:23` RequestStateUtility.get_request_state
- [x] `utilities/request/state.py:31` RequestStateUtility.set_request_state
- [x] `utilities/request/state.py:41` RequestStateUtility.update_request_state
- [x] `utilities/request/state.py:50` RequestStateUtility.pop_request_state
- [x] `utilities/request/state.py:58` RequestStateUtility.has_request_state
- [x] `utilities/request/state.py:64` RequestStateUtility.clear_request_state

### `utilities/response/body.py`

- [x] `utilities/response/body.py:24` ResponseBodyUtility.get_response_body
- [x] `utilities/response/body.py:34` ResponseBodyUtility.set_response_body
- [x] `utilities/response/body.py:43` ResponseBodyUtility.set_response_body_json
- [x] `utilities/response/body.py:50` ResponseBodyUtility.set_response_body_text
- [x] `utilities/response/body.py:55` ResponseBodyUtility.set_empty_response
- [x] `utilities/response/body.py:63` ResponseBodyUtility.get_response_body_size

### `utilities/response/cookie.py`

- [x] `utilities/response/cookie.py:25` ResponseCookieUtility.set_cookie
- [x] `utilities/response/cookie.py:62` ResponseCookieUtility.delete_cookie
- [x] `utilities/response/cookie.py:79` ResponseCookieUtility.clear_all_cookies
- [x] `utilities/response/cookie.py:84` ResponseCookieUtility.has_cookie

### `utilities/response/header.py`

- [x] `utilities/response/header.py:17` ResponseHeaderUtility.get_response_header
- [x] `utilities/response/header.py:27` ResponseHeaderUtility.get_all_response_headers
- [x] `utilities/response/header.py:34` ResponseHeaderUtility.set_response_header
- [x] `utilities/response/header.py:43` ResponseHeaderUtility.add_response_header
- [x] `utilities/response/header.py:50` ResponseHeaderUtility.remove_response_header
- [x] `utilities/response/header.py:60` ResponseHeaderUtility.has_response_header
- [x] `utilities/response/header.py:67` ResponseHeaderUtility.get_response_status
- [x] `utilities/response/header.py:72` ResponseHeaderUtility.set_response_status

### `utilities/response/state.py`

- [x] `utilities/response/state.py:23` ResponseStateUtility.get_response_state
- [x] `utilities/response/state.py:31` ResponseStateUtility.set_response_state
- [x] `utilities/response/state.py:41` ResponseStateUtility.update_response_state
- [x] `utilities/response/state.py:50` ResponseStateUtility.pop_response_state
- [x] `utilities/response/state.py:58` ResponseStateUtility.has_response_state
- [x] `utilities/response/state.py:64` ResponseStateUtility.clear_response_state

### `utilities/timing.py`

- [x] `utilities/timing.py:22` TimingUtility.configure_layer
- [x] `utilities/timing.py:27` TimingUtility.get_layer_config
- [x] `utilities/timing.py:32` TimingUtility.build_fields
- [x] `utilities/timing.py:51` async TimingUtility.run_timer
- [x] `utilities/timing.py:99` TimingUtility.run_timer_sync
- [x] `utilities/timing.py:147` TimingUtility.timer
- [ ] `utilities/timing.py:158` decorator
- [ ] `utilities/timing.py:164` async async_wrapper
- [ ] `utilities/timing.py:168` async _call
- [ ] `utilities/timing.py:187` sync_wrapper
- [ ] `utilities/timing.py:191` _call

### `utilities/urn.py`

- [x] `utilities/urn.py:28` URNUtility.generate_uuid4
- [x] `utilities/urn.py:33` URNUtility.generate_uuid
- [x] `utilities/urn.py:38` URNUtility.generate_ulid
- [x] `utilities/urn.py:48` URNUtility.generate_random_string
- [x] `utilities/urn.py:53` URNUtility.generate_urn
- [x] `utilities/urn.py:58` URNUtility.label

### `utilities/validation.py`

- [x] `utilities/validation.py:32` ValidationUtility.validate_none
- [x] `utilities/validation.py:40` ValidationUtility.validate_instance
- [x] `utilities/validation.py:61` ValidationUtility.validate_empty
- [x] `utilities/validation.py:70` ValidationUtility.validate_regex
- [x] `utilities/validation.py:77` ValidationUtility.validate_among
- [x] `utilities/validation.py:94` ValidationUtility.validate_urn
- [x] `utilities/validation.py:116` ValidationUtility.validate_id
- [x] `utilities/validation.py:123` ValidationUtility.validate_string
- [x] `utilities/validation.py:130` ValidationUtility.validate_bool
- [x] `utilities/validation.py:136` ValidationUtility.validate_int
- [x] `utilities/validation.py:142` ValidationUtility.validate_float
- [x] `utilities/validation.py:149` ValidationUtility.validate_decimal
- [x] `utilities/validation.py:159` ValidationUtility.validate_list
- [x] `utilities/validation.py:165` ValidationUtility.validate_dict
- [x] `utilities/validation.py:171` ValidationUtility.validate_tuple
- [x] `utilities/validation.py:177` ValidationUtility.validate_set
- [x] `utilities/validation.py:183` ValidationUtility.validate_code
- [x] `utilities/validation.py:197` ValidationUtility.validate_datetime
- [x] `utilities/validation.py:214` ValidationUtility.validate_email
- [x] `utilities/validation.py:228` ValidationUtility.validate_uuid
- [x] `utilities/validation.py:240` ValidationUtility.validate_url
- [x] `utilities/validation.py:258` ValidationUtility.validate_ip
- [x] `utilities/validation.py:270` ValidationUtility.validate_phone
- [x] `utilities/validation.py:286` ValidationUtility.validate_iban
- [x] `utilities/validation.py:300` ValidationUtility.format_iban
- [x] `utilities/validation.py:305` ValidationUtility.validate_ascii
- [x] `utilities/validation.py:314` ValidationUtility.validate_luhn
- [x] `utilities/validation.py:334` ValidationUtility.sanitize_html
- [x] `utilities/validation.py:341` ValidationUtility.strip_html_tags
- [x] `utilities/validation.py:348` ValidationUtility.validate_json_schema
- [x] `utilities/validation.py:367` ValidationUtility.label

### `utilities/webhook.py`

- [x] `utilities/webhook.py:16` async WebhookUtility.post
- [x] `utilities/webhook.py:75` async WebhookUtility.post_json
- [x] `utilities/webhook.py:81` WebhookUtility.label

### `web/_landing.py`

- [x] `web/_landing.py:90` _safe
- [x] `web/_landing.py:96` _http_method_class
- [x] `web/_landing.py:100` build_landing_page
- [x] `web/_landing.py:232` _admin_mounted
- [x] `web/_landing.py:236` _codegen_mounted

### `web/contenttypes.py`

- [ ] `web/contenttypes.py:26` ContentTypeRegistry.register
- [ ] `web/contenttypes.py:41` ContentTypeRegistry.get
- [ ] `web/contenttypes.py:44` ContentTypeRegistry.get_by_id
- [ ] `web/contenttypes.py:47` ContentTypeRegistry.all
- [ ] `web/contenttypes.py:50` ContentTypeRegistry.get_object
- [ ] `web/contenttypes.py:66` async ContentTypeRegistry.create_table
- [x] `web/contenttypes.py:155` get_content_type
- [ ] `web/contenttypes.py:165` get_object

### `web/email.py`

- [ ] `web/email.py:29` EmailMessage._build_mime
- [ ] `web/email.py:54` EmailMessage.recipients
- [ ] `web/email.py:60` async EmailBackend.send
- [ ] `web/email.py:64` async EmailBackend.close
- [ ] `web/email.py:85` async SmtpBackend.send
- [ ] `web/email.py:108` async SmtpBackend.close
- [ ] `web/email.py:113` async ConsoleBackend.send
- [ ] `web/email.py:121` async ConsoleBackend.close
- [ ] `web/email.py:129` async FileBackend.send
- [ ] `web/email.py:147` async FileBackend.close
- [ ] `web/email.py:151` get_email_backend
- [ ] `web/email.py:169` async send_email

### `web/forms.py`

- [x] `web/forms.py:29` FormField.render
- [x] `web/forms.py:78` Form._build_fields
- [x] `web/forms.py:84` Form.fields
- [x] `web/forms.py:87` Form.is_valid
- [x] `web/forms.py:108` Form.errors
- [x] `web/forms.py:112` Form.cleaned_data
- [x] `web/forms.py:115` Form.as_table
- [x] `web/forms.py:126` Form.as_p
- [x] `web/forms.py:134` Form.as_ul
- [x] `web/forms.py:142` Form.hidden_fields
- [x] `web/forms.py:163` EmailField._validate_email
- [x] `web/forms.py:182` IntegerField._validate_int
- [x] `web/forms.py:202` SelectField._validate_choice
- [x] `web/forms.py:214` TextAreaField.render

### `web/gis.py`

- [ ] `web/gis.py:19` Geometry.wkt
- [ ] `web/gis.py:35` Point.wkt
- [ ] `web/gis.py:51` LineString.wkt
- [ ] `web/gis.py:62` Polygon.wkt
- [ ] `web/gis.py:76` MultiPoint.wkt
- [ ] `web/gis.py:87` MultiLineString.wkt
- [ ] `web/gis.py:101` MultiPolygon.wkt
- [ ] `web/gis.py:118` GeometryCollection.wkt
- [ ] `web/gis.py:153` SpatialQuery.distance
- [ ] `web/gis.py:156` SpatialQuery.within
- [ ] `web/gis.py:159` SpatialQuery.intersects
- [ ] `web/gis.py:162` SpatialQuery.contains
- [ ] `web/gis.py:165` SpatialQuery.bbox
- [x] `web/gis.py:169` haversine_distance
- [ ] `web/gis.py:181` earth_distance
- [x] `web/gis.py:185` to_geojson

### `web/htmx.py`

- [ ] `web/htmx.py:51` HtmxDetails._ensure
- [x] `web/htmx.py:74` HtmxDetails.request
- [x] `web/htmx.py:81` HtmxDetails.boosted
- [x] `web/htmx.py:87` HtmxDetails.current_url
- [x] `web/htmx.py:93` HtmxDetails.history_restore_request
- [x] `web/htmx.py:99` HtmxDetails.prompt
- [x] `web/htmx.py:105` HtmxDetails.target
- [x] `web/htmx.py:111` HtmxDetails.trigger
- [x] `web/htmx.py:117` HtmxDetails.trigger_name
- [x] `web/htmx.py:178` HXRedirect
- [x] `web/htmx.py:188` HXRefresh
- [x] `web/htmx.py:197` HXLocation
- [x] `web/htmx.py:207` HXSwap
- [x] `web/htmx.py:217` HXRetarget
- [x] `web/htmx.py:229` HXReselect
- [x] `web/htmx.py:241` HXPushUrl

### `web/i18n.py`

- [ ] `web/i18n.py:14` set_locale
- [ ] `web/i18n.py:18` get_locale
- [ ] `web/i18n.py:39` Translations._load_available
- [ ] `web/i18n.py:53` Translations.available_locales
- [ ] `web/i18n.py:56` Translations.gettext
- [ ] `web/i18n.py:63` Translations.ngettext
- [ ] `web/i18n.py:70` Translations.pgettext
- [ ] `web/i18n.py:78` _get_intl
- [ ] `web/i18n.py:90` gettext
- [ ] `web/i18n.py:97` ngettext
- [ ] `web/i18n.py:104` pgettext
- [ ] `web/i18n.py:136` LocaleMiddleware._parse_accept_language
- [ ] `web/i18n.py:159` async LocaleMiddleware.process
- [x] `web/i18n.py:210` format_number
- [x] `web/i18n.py:221` format_date
- [ ] `web/i18n.py:238` format_currency

### `web/negotiation.py`

- [x] `web/negotiation.py:7` parse_accept
- [x] `web/negotiation.py:32` best_match

### `web/routing.py`

- [ ] `web/routing.py:78` _join_paths
- [x] `web/routing.py:85` route
- [ ] `web/routing.py:115` decorator
- [ ] `web/routing.py:148` get
- [ ] `web/routing.py:152` post
- [ ] `web/routing.py:156` put
- [ ] `web/routing.py:160` delete
- [ ] `web/routing.py:164` patch
- [ ] `web/routing.py:168` head
- [ ] `web/routing.py:172` options
- [ ] `web/routing.py:242` is_controller
- [x] `web/routing.py:248` _resolve_str
- [x] `web/routing.py:271` _resolve_list
- [x] `web/routing.py:284` _resolve_bool
- [x] `web/routing.py:292` _resolve_optional
- [x] `web/routing.py:304` controller_to_router
- [ ] `web/routing.py:428` async _LifecycleHookMiddleware.process
- [ ] `web/routing.py:467` RouteGroup._route
- [ ] `web/routing.py:473` decorator
- [ ] `web/routing.py:497` RouteGroup.get
- [ ] `web/routing.py:500` RouteGroup.post
- [ ] `web/routing.py:503` RouteGroup.put
- [ ] `web/routing.py:506` RouteGroup.delete
- [ ] `web/routing.py:509` RouteGroup.patch
- [ ] `web/routing.py:512` RouteGroup.head
- [ ] `web/routing.py:515` RouteGroup.options
- [ ] `web/routing.py:518` RouteGroup.flush
- [ ] `web/routing.py:542` Router.add_middleware
- [ ] `web/routing.py:545` Router.before_request
- [ ] `web/routing.py:549` Router.after_request
- [ ] `web/routing.py:553` Router.group
- [ ] `web/routing.py:563` Router.exception_handler
- [ ] `web/routing.py:564` decorator
- [ ] `web/routing.py:570` Router.get
- [ ] `web/routing.py:573` Router.post
- [ ] `web/routing.py:576` Router.put
- [ ] `web/routing.py:579` Router.delete
- [ ] `web/routing.py:582` Router.patch
- [ ] `web/routing.py:585` Router.head
- [ ] `web/routing.py:588` Router.options
- [ ] `web/routing.py:591` Router._route
- [ ] `web/routing.py:622` decorator
- [x] `web/routing.py:658` Router.include_route
- [ ] `web/routing.py:760` Router.include_router
- [ ] `web/routing.py:829` Router.include_controller

### `web/static_pipeline.py`

- [x] `web/static_pipeline.py:38` StaticPipeline.collect
- [x] `web/static_pipeline.py:55` StaticPipeline.version
- [x] `web/static_pipeline.py:84` StaticPipeline.compress
- [x] `web/static_pipeline.py:103` StaticPipeline.load_manifest
- [x] `web/static_pipeline.py:108` StaticPipeline.resolve_url
- [x] `web/static_pipeline.py:114` async StaticPipeline.upload_to_s3
- [x] `web/static_pipeline.py:133` async StaticPipeline.upload_to_gcs
- [x] `web/static_pipeline.py:148` async StaticPipeline.upload_to_azure

### `web/staticfiles.py`

- [x] `web/staticfiles.py:11` _file_etag
- [x] `web/staticfiles.py:18` _parse_range
- [ ] `web/staticfiles.py:107` _header_value
- [ ] `web/staticfiles.py:199` _guess_mime
- [ ] `web/staticfiles.py:205` _not_found

### `web/templating.py`

- [x] `web/templating.py:22` Jinja2Templates.TemplateResponse
- [x] `web/templating.py:33` Jinja2Templates.render
- [x] `web/templating.py:37` Jinja2Templates.get_template

### `web/uploads.py`

- [ ] `web/uploads.py:27` async UploadFile.read
- [ ] `web/uploads.py:30` async UploadFile.write
- [ ] `web/uploads.py:33` async UploadFile.seek
- [ ] `web/uploads.py:36` async UploadFile.close
- [ ] `web/uploads.py:148` Form.required
- [x] `web/uploads.py:161` parse_multipart
- [ ] `web/uploads.py:234` _extract_boundary
- [ ] `web/uploads.py:245` _parse_content_disposition
- [ ] `web/uploads.py:260` _parse_header_value

### `web/versioning.py`

- [ ] `web/versioning.py:46` VersionedRouter.get
- [ ] `web/versioning.py:49` VersionedRouter.post
- [ ] `web/versioning.py:52` VersionedRouter.put
- [ ] `web/versioning.py:55` VersionedRouter.delete
- [ ] `web/versioning.py:58` VersionedRouter.patch
- [ ] `web/versioning.py:61` VersionedRouter.options
- [ ] `web/versioning.py:64` VersionedRouter.head
- [ ] `web/versioning.py:69` VersionedRouter._register
- [ ] `web/versioning.py:73` decorator

### `web/viewsets.py`

- [x] `web/viewsets.py:26` async ViewSet.list
- [x] `web/viewsets.py:29` async ViewSet.create
- [x] `web/viewsets.py:32` async ViewSet.retrieve
- [x] `web/viewsets.py:35` async ViewSet.update
- [x] `web/viewsets.py:38` async ViewSet.partial_update
- [x] `web/viewsets.py:41` async ViewSet.destroy
- [x] `web/viewsets.py:44` ViewSet.as_view
- [x] `web/viewsets.py:45` async view
- [x] `web/viewsets.py:63` async ModelViewSet.get_queryset
- [x] `web/viewsets.py:66` async ModelViewSet.get_object
- [x] `web/viewsets.py:75` async ListModelMixin.list
- [x] `web/viewsets.py:108` Router.register
- [x] `web/viewsets.py:162` Router.routes
- [x] `web/viewsets.py:165` Router.install
- [x] `web/viewsets.py:183` async BrowsableAPIMiddleware.process

### `web/webdav.py`

- [x] `web/webdav.py:33` WebDAVMiddleware._resolve_path
- [x] `web/webdav.py:44` WebDAVMiddleware._format_propfind_xml
- [x] `web/webdav.py:76` WebDAVMiddleware._format_propfind_multi
- [x] `web/webdav.py:85` async WebDAVMiddleware.process

### `websocket/auth.py`

- [ ] `websocket/auth.py:19` async WSAuthMiddleware.authenticate
- [ ] `websocket/auth.py:49` require_ws_auth

### `websocket/client.py`

- [ ] `websocket/client.py:23` ConnectionPool.register
- [ ] `websocket/client.py:32` ConnectionPool.next
- [ ] `websocket/client.py:41` ConnectionPool.mark_disconnected
- [ ] `websocket/client.py:49` ConnectionPool.mark_connected
- [ ] `websocket/client.py:57` ConnectionPool.remove
- [ ] `websocket/client.py:63` ConnectionPool.active_count
- [ ] `websocket/client.py:68` ConnectionPool.total_count

### `websocket/codec.py`

- [ ] `websocket/codec.py:16` register_codec
- [ ] `websocket/codec.py:20` get_codec
- [ ] `websocket/codec.py:28` BinaryCodec.encode
- [ ] `websocket/codec.py:31` BinaryCodec.decode
- [ ] `websocket/codec.py:34` BinaryCodec.detect
- [ ] `websocket/codec.py:41` JSONCodec.encode
- [ ] `websocket/codec.py:45` JSONCodec.decode
- [ ] `websocket/codec.py:49` JSONCodec.detect
- [ ] `websocket/codec.py:61` MsgPackCodec.encode
- [ ] `websocket/codec.py:66` MsgPackCodec.decode
- [ ] `websocket/codec.py:71` MsgPackCodec.detect
- [ ] `websocket/codec.py:88` auto_decode
- [ ] `websocket/codec.py:95` auto_encode

### `websocket/flow_control.py`

- [ ] `websocket/flow_control.py:23` BackpressureController.increment
- [ ] `websocket/flow_control.py:30` BackpressureController.decrement
- [ ] `websocket/flow_control.py:38` BackpressureController.is_throttled
- [ ] `websocket/flow_control.py:43` BackpressureController.can_resume
- [ ] `websocket/flow_control.py:48` BackpressureController.pending_count
- [ ] `websocket/flow_control.py:53` async BackpressureController.check_or_raise
- [ ] `websocket/flow_control.py:57` BackpressureController.remove
- [ ] `websocket/flow_control.py:62` BackpressureController.clear_all

### `websocket/heartbeat.py`

- [ ] `websocket/heartbeat.py:21` async HeartbeatManager.start
- [ ] `websocket/heartbeat.py:25` async _beat
- [ ] `websocket/heartbeat.py:51` async HeartbeatManager.pong_received
- [ ] `websocket/heartbeat.py:54` async HeartbeatManager.stop
- [ ] `websocket/heartbeat.py:64` async HeartbeatManager.stop_all

### `websocket/lifecycle.py`

- [ ] `websocket/lifecycle.py:26` async GracefulShutdown.start_shutdown
- [ ] `websocket/lifecycle.py:44` GracefulShutdown.is_drain_expired
- [ ] `websocket/lifecycle.py:49` GracefulShutdown.connection_closed
- [ ] `websocket/lifecycle.py:53` GracefulShutdown.register_connection
- [ ] `websocket/lifecycle.py:56` GracefulShutdown.remove_connection
- [ ] `websocket/lifecycle.py:61` GracefulShutdown.shutting_down
- [ ] `websocket/lifecycle.py:66` GracefulShutdown.reset

### `websocket/multi_server.py`

- [ ] `websocket/multi_server.py:10` async MultiServerBackend.publish
- [ ] `websocket/multi_server.py:13` async MultiServerBackend.subscribe
- [ ] `websocket/multi_server.py:16` async MultiServerBackend.unsubscribe
- [ ] `websocket/multi_server.py:19` async MultiServerBackend.close
- [ ] `websocket/multi_server.py:30` async RedisPubSubBackend.publish
- [ ] `websocket/multi_server.py:40` async RedisPubSubBackend.subscribe
- [ ] `websocket/multi_server.py:53` async RedisPubSubBackend.unsubscribe
- [ ] `websocket/multi_server.py:58` async RedisPubSubBackend._listener
- [ ] `websocket/multi_server.py:81` async RedisPubSubBackend.close
- [ ] `websocket/multi_server.py:101` async NATSBackend.publish
- [ ] `websocket/multi_server.py:113` async NATSBackend.subscribe
- [ ] `websocket/multi_server.py:119` async _handler
- [ ] `websocket/multi_server.py:129` async NATSBackend.unsubscribe
- [ ] `websocket/multi_server.py:134` async NATSBackend.close

### `websocket/presence.py`

- [ ] `websocket/presence.py:37` async PresenceTracker.track
- [ ] `websocket/presence.py:56` async PresenceTracker.untrack
- [ ] `websocket/presence.py:74` async PresenceTracker.touch
- [ ] `websocket/presence.py:79` PresenceTracker.get_room_users
- [ ] `websocket/presence.py:88` PresenceTracker.get_user_rooms
- [ ] `websocket/presence.py:93` PresenceTracker.room_count
- [ ] `websocket/presence.py:98` PresenceTracker.total_connections
- [ ] `websocket/presence.py:103` PresenceTracker.active_rooms
- [ ] `websocket/presence.py:108` async PresenceTracker.cleanup_idle
- [ ] `websocket/presence.py:117` async PresenceTracker._broadcast_presence

### `websocket/rate_limit.py`

- [ ] `websocket/rate_limit.py:31` RateLimiter._key
- [ ] `websocket/rate_limit.py:34` RateLimiter.check
- [ ] `websocket/rate_limit.py:46` async RateLimiter.check_or_raise
- [ ] `websocket/rate_limit.py:50` RateLimiter.reset
- [ ] `websocket/rate_limit.py:55` RateLimiter.remaining

### `websocket/reconnection.py`

- [ ] `websocket/reconnection.py:33` ReconnectionHelper.create_resume_token
- [ ] `websocket/reconnection.py:40` ReconnectionHelper.resolve_token
- [ ] `websocket/reconnection.py:48` ReconnectionHelper.record_message
- [ ] `websocket/reconnection.py:64` ReconnectionHelper.get_missed
- [ ] `websocket/reconnection.py:73` ReconnectionHelper.cleanup
- [ ] `websocket/reconnection.py:80` ReconnectionHelper.last_seq
- [ ] `websocket/reconnection.py:86` json_msg

### `websocket/reliability.py`

- [ ] `websocket/reliability.py:24` MessageAckTracker.send
- [ ] `websocket/reliability.py:35` MessageAckTracker.ack
- [ ] `websocket/reliability.py:41` MessageAckTracker.nack
- [ ] `websocket/reliability.py:53` MessageAckTracker.pending_messages
- [ ] `websocket/reliability.py:58` MessageAckTracker.is_delivered
- [ ] `websocket/reliability.py:63` MessageAckTracker.check_timeouts
- [ ] `websocket/reliability.py:68` MessageAckTracker.clear

### `websocket/rpc.py`

- [ ] `websocket/rpc.py:16` RPCServer.register
- [ ] `websocket/rpc.py:19` async RPCServer.handle_message
- [ ] `websocket/rpc.py:40` async RPCServer._send_response
- [ ] `websocket/rpc.py:44` async RPCServer._send_error
- [ ] `websocket/rpc.py:55` RPCClient._next_id
- [ ] `websocket/rpc.py:59` async RPCClient.call
- [ ] `websocket/rpc.py:76` async RPCClient.handle_response
- [ ] `websocket/rpc.py:97` rpc_method
- [ ] `websocket/rpc.py:98` decorator

### `websocket/security.py`

- [ ] `websocket/security.py:22` OriginValidator.validate
- [ ] `websocket/security.py:35` OriginValidator.allowed_origins

### `websocket/typing.py`

- [ ] `websocket/typing.py:29` async TypingIndicators.typing_start
- [ ] `websocket/typing.py:42` async TypingIndicators.typing_stop
- [ ] `websocket/typing.py:51` TypingIndicators.is_typing

### `websocket/validation.py`

- [ ] `websocket/validation.py:26` MessageSizeValidator.validate_text
- [ ] `websocket/validation.py:33` MessageSizeValidator.validate_bytes
- [ ] `websocket/validation.py:53` SchemaValidator.register_schema
- [ ] `websocket/validation.py:59` SchemaValidator.validate
