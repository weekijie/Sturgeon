Post-Deploy Checklist

Overflow regressions
Search Modal logs for vLLM max token overflow; retrying and parameter=max_tokens.
Target: near-zero for normal demo flows (/differential, /summary).
Truncation/JSON stability
Search for JSON parse error and JSON successfully repaired from truncated output.
Target: no repairs in standard 3-case run; at most rare retries with successful parse.
Latency SLO snapshot (p50/p95)
Track endpoint durations from structured logs:
/analyze-image: target p50 < 90s, p95 < 120s
/differential: target p50 < 110s, p95 < 150s
/debate-turn: target p50 < 45s, p95 < 65s
/summary: target p50 < 110s, p95 < 150s
Compare against your pre-patch baseline (~121s / 161s / 45–61s / 146s).
Retry rate
Count occurrences of concise retry paths:
differential-concise-retry
summary-concise-retry
Target: low but non-zero is okay; persistent high means caps are too tight.
RAG quality drift
Inspect rag_audit sources for melanoma cases.
Target: mostly melanoma/AAD sources; minimal irrelevant USPSTF breast/colorectal in melanoma turns.
Guideline link quality
Verify frontend debate citations remain valid http(s) and clickable.
Target: no empty-link behavior, no same-page accidental links.
Warmup credit behavior
Confirm warmup does not auto-run unless intended (NEXT_PUBLIC_WARMUP_AUTOSTART).
Confirm poll cap behavior: after max attempts, toast shows paused state.
Check Modal invocation volume from /health; target reduced idle probing.
Cold/warm practical UX
Cold path: first Analyze may take 2–3 min, but should complete.
Warm path: subsequent requests in same session should be significantly faster.
Cost guardrail
Daily check Modal spend delta.
Target: no long idle-cost tails; spend correlates with real test activity only.
Functional correctness smoke
Run 3 demo cases end-to-end:
Upload + analyze image
Differential generates 3–4 diagnoses with evidence
2 debate turns with citations
Summary returns valid structured fields
Error surface
Ensure frontend still shows meaningful errors on 500/504 and retry UX remains usable.