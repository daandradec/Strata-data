# Reload-safe Strata compaction extension
Make the approved Strata diagnostics and first-compaction correction take effect after Pi /reload, without changing installed packages, settings or sessions.
Branch: feat/strata-compaction; delivery: local work-unit commits only; checks: Node tests and installed public Pi loader in the same process.

## Specs

- S1 — Latest user report, verbatim: "no se arreglo, apesar de seguir tus pasos, sigue saliendo:
Warning: Strata compaction cancelled without a custom checkpoint. Check the count
 endpoint/model availability, then retry /compact; cancellation and bounded-summary limits
 also cancel safely.

 Error: Compaction cancelled"
- S2 — Preserve the earlier authorized diagnostic outcome: "Sí, agregar el diagnóstico seguro". Keep fixed cause codes/stages and do not expose conversations, credentials, paths, URLs or raw exceptions. Preserve the approved first-compaction null guard and safe cancellation; source corrections must reach the loaded hook.
- S3 — Preserve the original implementation authorization: "vamos con A y B, que el problema manual de una sesion trabada justamente lo solucione cambiando de modelo pero igual quiero que strata siga sirviendo." Retain exact-model gating, native boundaries/files, context131072/reserve32768, and other-model behavior. No edits to installed node_modules, global settings, or user session records are needed for this loading fix.

## Tasks

- T1 [S1-S2] Reproduce stale loading with the installed public loader, helper edited between two loads in one process. Route: parent bounded probe; status: done; commit: 3d92b9def9e62dc255f3ce3b35dd872caa6feab7 (persistent regression); evidence: RED exit1, second load still executes markerA after helper changed to markerB, JITI_FS_CACHE=0.
- T2 [S1-S3] Implement a supported reload-safe module strategy and retain the approved diagnostic/first-compaction changes. Route: bounded writer (context backstop), after read-only loader map; status: done; commit: 3d92b9def9e62dc255f3ce3b35dd872caa6feab7; evidence: installed public-loader GREEN5/5, full suite63/63, no skips.
- T3 [S1-S3] Pin same-process reload regression for relevant helper/entry changes, run focused/full/public-loader/no-op checks and assess actual diff. Route: writer checks plus parent assessment/spot-check, independent verifier only for a named risk; status: done; commit: 3d92b9def9e62dc255f3ce3b35dd872caa6feab7; evidence: parent reviewed regression/imports, confirmed core unchanged and assessed both normalized source work units medium/reviewDue:false.
- T4 [S1] Confirm the affected panel loads the new hook and reports success or a safe code/stage. Route: human panel action after verified loading fix; status: done; commit: not_applicable (human runtime confirmation); evidence: user followed the steps and confirmed successful compaction in L10.

## Log

L1 — Latest report, verbatim:
no se arreglo, apesar de seguir tus pasos, sigue saliendo:
Warning: Strata compaction cancelled without a custom checkpoint. Check the count
 endpoint/model availability, then retry /compact; cancellation and bounded-summary limits
 also cancel safely.

 Error: Compaction cancelled

L2 — Earlier context: the user reported the same cancellation on both automatic and manual compaction and explicitly approved safe diagnostic changes. The diagnostic change and no-checkpoint guard are approved existing working-tree edits in adapter.mjs, adapter.test.mjs and README.md; they must not be discarded. Prior final suite58/58, syntax and base differential passed. This did not prove in-process reload.

L3 — Current global settings readback: exactly one registration at E:/Strata-data/extensions/strata-compaction/index.ts; reserve32768. Current index.ts, adapter.mjs and core.mjs contain no old generic warning. Primary Nodev26.12.1. No direct access to the other panel's process or broader sessions has been authorized.

L4 — Parent reproduction: copy current index.ts/adapter.mjs/core.mjs into a fresh temp directory; load via discoverAndLoadExtensions; pre-aborted synthetic hook emits markerA; rewrite adapter prefix to markerB; call discoverAndLoadExtensions again in SAME process. It still emits markerA, assertion exit1. JITI_FS_CACHE=0, no model/network/session calls, scratch removed. This demonstrates native helper staleness despite disabled disk cache. Existing fresh-process tests missed it. Pi root: C:/Users/daand/AppData/Local/gentle-shell/versions/4.3.0-1.2.0/node_modules/.pnpm/@earendil-works+pi-coding-a_cc01c331fc629de0dd103b0356c0a9b4/node_modules/@earendil-works/pi-coding-agent.

L5 — Explorer map, parent spot-checked loader.js450-511: Pi creates fresh Jiti with moduleCache:false; embedded loader forces tryNative:false, unbundled loader uses aliases and default tryNative. Matching Jiti2.7 defaults tryNative false on ordinary Node, not based on native TS capability; explicit JITI_TRY_NATIVE=true can override unbundled behavior. Parent environment has neither JITI_TRY_NATIVE nor JITI_FS_CACHE set. Candidate: transform entire index.ts→adapter.ts→core.ts chain, test both helper edits in the same process under normal filesystem cache. Keep registered entry stable. No global environment/settings/cache monkey-patching, query-string loaders, new dependencies, algorithm or budget changes. Confirm with actual public loader; a rename alone is not proof.

L6 — Worker mvnaifg3-8-69wt completed: entire implementation chain migrated to TS without changing registered index.ts. Persistent public-loader regression RED exit1 on MJS then GREEN exit0 (5/5), normal cache/default policy; full suite63/63 exit0 with STRATA_PI_ROOT set, no skips. Covers adapter/core/entry edits in same process, first/prior checkpoint metadata/files, cancellation privacy/counters and exact-model no-op. Core source identical to HEAD after LF normalization; parent independently confirmed. Syntax helper/tests checks passed. Raw node --check index.ts failed on its pre-existing import type syntax (also with strip-types flag); actual Pi public loader compiled/loaded entry successfully. No session/model/network access or global changes. Default run without STRATA_PI_ROOT explicitly skips one loader test and is not proof. Memory877/878.

L7 — Parent reviewed the persistent test and docs. Combined extension diff is454 authored lines including earlier approved diagnostics/first-checkpoint fix. Plan: two coherent local work units, diagnostic/first-checkpoint correction with its tests/docs, then atomic TS reload chain with regression/docs/tracking. Do not separate tests from either behavior or alter actual working-tree runtime while staging the first unit. Initial assess of unnormalized working changes returned unassessable because untracked files need declaration; its fallback plan accepts writer self-verification, no separate verifier. This is recorded as a failed assessment, not a successful review or reviewDue:false.

L8 — Local source work units committed: 4d7f6d96983980d2868404fdd6c0d4fd3e9f2647 (diagnostic/first-checkpoint correction,195 additions20 deletions=215 authored lines) and 3d92b9def9e62dc255f3ce3b35dd872caa6feab7 (atomic TS reload chain plus regression/docs,232 additions19 deletions=251 rename-aware authored lines). First unit staged from exact earlier verified adapter hash424f79d0f1fcfffa069344b68791399c67798c35395014b42a9c301dd31960a5 and matching test imports; intermediate docs correctly require process restart for its MJS layout. Active TS working-tree files were never replaced. No publishing.

L9 — Native committed-range assessments: unit1 base0c97d26d1c8abc32a1c552cd0ad19d19204bf5ee, medium/215lines/reviewDue:false; unit2 base4d7f6d96983980d2868404fdd6c0d4fd3e9f2647, medium/975 native raw lines (includes rename accounting)/reviewDue:false. Both return writerSelfVerification:true, independentVerifier:false; no review authority started or approval claimed. Initial untracked-file assessment failure is retained above; normalized committed candidates were assessed separately, not a replay of authority. Risk: none in Task Size high-risk list: target-model hook only, unchanged core algorithm, no outside consumers changed, stable registered entry and explicit no-op/differential checks. T4 is the sole remaining missing proof; do not claim the affected user's original compaction is fixed before its next result. Final tracking evidence is a small separate local documentation commit.

L10 — User confirmation, verbatim: "lo hice y ya funciono y la compactacion funciono perfecto, queda cerrado si?" The affected-panel runtime proof is now satisfied. T1-T4 are done; the follow-up is closed with no remaining blockers. No further code/configuration changes or functional test reruns are needed for this bookkeeping closure.
