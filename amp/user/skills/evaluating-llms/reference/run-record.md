# Lightweight investigation record

Use only the fields needed for this investigation. This is an evidence/decision record, not a mandatory acceptance checklist. Keep generations append-only; never store secrets or data the authorization excludes.

## Investigation

- Application/user outcome and decision being explored:
- Actual deployed baseline, including parser, failure policy, fallbacks, and retries:
- Owner-approved constraints and source of approval (budget, privacy, safety):
- Provisional agent assumptions, metrics, thresholds, and rubric; what remains open:
- Data provenance/permission, label quality, known gaps, and evidence storage/access:
- Authorized total budget, prior spend, unresolved liability, and remaining headroom:

## Experiment generation / run ID

- Question and competing hypotheses:
- Smallest test that distinguishes them; expected information gained:
- Prior generation and what changed, why, and what stayed controlled:
- Development/diagnostic or confirmation; case IDs/slices, selection, and any prior exposure:
- Model/provider/version; exact prompt/context/tools; schema/parser/runtime revision:
- Token caps, sampling/reasoning settings, timeouts, retry/fallback policy:
- Comparison arms and relevant resource constraints; why unequal settings are comparable:
- Planned repetitions; variability/uncertainty to assess:
- Estimated upper bound, concurrency reservations, retries, and unresolved-attempt reserve:
- Evidence links for versioned configuration, permitted raw traces, and per-case outcomes:

## Results

Record per attempt, including failed and pending attempts; group by case and arm:

| Case / slice / repeat | Arm / generation | Judgment | Finish / tool / parse status | Effective app outcome / fallback | Latency | Actual cost or reserved liability |
|---|---|---|---|---|---|---|

- Paired wins/losses, aggregates with denominators, exclusions, and important slices:
- No-verdicts, retries, fallbacks, effective reliability, and user impact:
- Variation/uncertainty and judge/label validation, including disagreements:
- Observed facts vs hypothesized causes; interventions performed and remaining confounds:
- Spend reconciled across all generations, including failed calls and unresolved reserves:
- Next informative test and its estimate; if stopping, resource reason vs capability conclusion:

## Confirmation and recommendation (when warranted)

- Developed hypothesis and proposed decision:
- Criteria: owner-approved vs proposed; rationale and safety constraints:
- Fresh/held-out evidence and limits; tuning exposure or leakage:
- Practical tradeoffs, unresolved questions, and uncertainty:
- Conclusion scoped to setup/task: criterion failed / not ready to promote / not worth further investigation / other:
- Recommendation and owner decision needed; production authorization remains separate:
- Later revisions/overrides with attribution and links; preserve previous result:
