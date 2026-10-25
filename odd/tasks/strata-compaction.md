# Strata bounded compaction
Implement the approved early-compaction setting and bounded summarization for Strata without editing installed packages or sessions.
Branch: feat/strata-compaction; delivery: local work-unit commits, no publication requested; runner: Node.js built-in test runner (integration command to be confirmed).

## Specs

- S1 — Original reported failure: "cuando utilizo strata aqui en gentle-shell y el contexto alcanza el tope mas alla del 90-95% siempre me sale este mensaje de error cuandoi ntenta autocompactar o cuando yo mismo escribo el comando de /compact, audita como podriamos corregirlo: Error: 400: {\"type\":\"invalid_request_error\",\"message\":\"prompt (154177 tokens) + max tokens (1) exceeds the context (131072);\n requests are never truncated. Send a smaller max_tokens (at most 0 here), or add \"fit_max_tokens\": true to the model's\n strata-<model>.json to shorten it to the room left (#545)\"}"
- S2 — Implementation authorization: "vamos con A y B, que el problema manual de una sesion trabada justamente lo solucione cambiando de modelo pero igual quiero que strata siga sirviendo."
- S3 — Approved A: merge `compaction.modelOverrides["strata/qwen3.8-flash-next-iq3_xxs"].reserveTokens = 32768` into `C:/Users/daand/.gentle-shell/agent/settings.json`, preserving all other settings. Approved B: budget the final summary prompt and summarize oversized input in bounded blocks, including oversized individual items; do not persist partial compaction after failure.
- S4 — Explicit write authorization: "Sí, autorizar esos cambios" in response to "¿Autorizás modificar C:/Users/daand/.gentle-shell/agent/settings.json para agregar la reserva de 32.768 tokens de Strata y registrar la extensión local de compactación, conservando los demás ajustes y dejando un respaldo del archivo en E:/Strata-data? No modificaré los paquetes instalados ni tus sesiones."

## Tasks

- T1 [S2-S4] Apply the exact-model reserve with an in-project settings backup and preservation checks. Route: inline (small configuration edit); status: pending; commit: pending.
- T2 [S1-S3] Implement and test bounded summary input/chunk reduction, including huge items and failure/abort handling. Route: delegated writer (measured context backstop); status: pending; commit: pending.
- T3 [S1-S4] Integrate through the supported Strata-only Pi compaction hook, preserve native retained boundaries and file tracking, and document operation. Route: delegated writer (measured context backstop), after T2; status: pending; commit: pending.
- T4 [S1-S4] Run applicable tests, assess actual diff, perform required verification, and register the verified extension without changing unrelated models/settings. Route: parent orchestration; status: pending; commit: pending.

## Log

L1 — Original request, verbatim:
cuando utilizo strata aqui en gentle-shell y el contexto alcanza el tope mas alla del 90-95% siempre me sale este mensaje de error cuandoi ntenta autocompactar o cuando yo mismo escribo el comando de /compact, audita como podriamos corregirlo: Error: 400: {"type":"invalid_request_error","message":"prompt (154177 tokens) + max tokens (1) exceeds the context (131072);
 requests are never truncated. Send a smaller max_tokens (at most 0 here), or add \"fit_max_tokens\": true to the model's
 strata-<model>.json to shorten it to the room left (#545)"}

L2 — Implementation request, verbatim:
vamos con A y B, que el problema manual de una sesion trabada justamente lo solucione cambiando de modelo pero igual quiero que strata siga sirviendo.

L3 — Evidence from the completed audit: provider and server both advertise 131072; model maxTokens is 8192; no Strata-specific compaction override. Pi may clamp summary output to one token without shrinking input. The summary has no global input budget. Strata never truncates an oversized prompt. The historical request's exact origin remains unproven.

L4 — Explicit user decision: "Sí, autorizar esos cambios" for writing agent settings to apply A and register B, with an in-project backup and preservation of other settings; no changes to installed packages or sessions.

L5 — Feasibility confirmed by read-only exploration: a supported local Pi extension can restrict itself to Strata without patching versioned node_modules. Return cancel:true on any failure to prevent native fallback; preserve native retention boundaries, previous summary and cumulative file-operation tracking (including previous custom-hook details). Use the public modelRegistry.complete API with thinking disabled; count the complete simple system/user prompt through Strata's count_tokens route with matching template settings. The installed package contains dist/docs/examples but no source checkout or upstream test suite. The project has no Git metadata; establish lightweight local tracking that excludes model binaries, logs, caches, backups and existing user data. No push, PR or dependency installation is planned. Live verification must use isolated transient state, never the user's conversation. Native overflow recovery may add its own omission entries before this hook; the extension guarantees no partial custom compaction is persisted, not zero native bookkeeping.
