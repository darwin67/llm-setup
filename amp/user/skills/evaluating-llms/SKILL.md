---
name: evaluating-llms
description: Investigates LLM suitability for applications through bounded, evidence-preserving experiments. Use for model replacement, prompt/context/token/tool changes, classifiers, rankers, safety gates, and agents.
---

# Evaluating LLMs

Preserve evidence, revise assumptions, and do not rush to conclusions. Evaluate the application-shaped setup, not a model name in isolation.

## Working posture

- Be curious and disciplined. Start with a question and the smallest informative test, not a binding acceptance framework before understanding the problem.
- Stabilize variables **within an individual experiment**, not the whole investigation. Revise prompts, context, metrics, and provisional thresholds as understanding improves; version changes and retain earlier results. Never silently rewrite evidence or relabel a tuned rerun as an independent test.
- Separate owner-approved requirements from agent-proposed rubrics, stop rules, thresholds, and recommendations. Label proposals as provisional; never turn them into owner decisions by repetition. Do not require better-on-every-metric unless explicitly required.
- Keep three conclusions distinct: **a tested criterion failed**, **not ready to promote**, and **not worth investigating further**. None automatically implies the next. A legitimate negative result remains valid for its tested scope; do not dismiss it or generalize it across unrelated tasks.
- Firm boundaries are the explicit budget, privacy/data-handling rules, and safety requirements. Evaluation is not authorization to ship, change production, weaken safeguards, or spend more.

## 1. Ground the question in the application

Inspect the actual caller, serialized inputs, model configuration, tools, parser, and downstream behavior before diagnosing capability. Establish:

- What users need; the decision/output contract; what a wrong answer, abstention, or unavailable answer causes.
- The operational baseline: the deployed configuration and its no-verdicts, fallbacks, retries, latency, costs, and user experience. Preserve it even when also comparing a corrected or tuned baseline.
- Which constraints the owner actually approved, which tradeoffs remain open, what evidence exists, and how much authorized budget remains. Ask only for essential missing authorization or information; otherwise state assumptions and proceed with reversible investigation.
- Relevant cases and slices, including ambiguous inputs and boundary cases. Check label quality and whether the model receives the information needed to answer. Do not invent requester facts or substitute synthetic context for missing real context without labeling it.

For agents, include the full workflow: tool availability/results, permissions, state, recovery paths, task completion, and user interventions—not just the final text or isolated model calls.

## 2. Run the smallest informative experiment

Write a short question, competing hypotheses, and a test that can distinguish them. Use [the run record](reference/run-record.md) when useful; scale documentation to the decision, not a universal harness.

- Use controlled comparisons on matched cases/context/tools to isolate a change. Record model/version, prompt, context, schema/parser, token limits, sampling/reasoning settings, and resource constraints.
- Also test reasonably tuned per-model configurations when informative. Equal effort labels or settings need not mean equivalent compute or behavior. Explain configuration/resource differences; compare under comparable authorized cost, latency, or other relevant constraints rather than forcing identical knobs.
- Estimate the run first. Reserve an upper bound per attempt, including retries, pending requests, and unresolved/time-out attempts; reconcile actual charges without erasing unknown liability. Enforce the cap before launching concurrent work. Count failed calls too. Do not retry blindly or spend beyond authorization.
- Capture raw requests/responses and finish reasons, tool outcomes, parse/no-verdict status, effective application outcomes, latency, tokens/costs, and case IDs, subject to data-handling rules. Redact or restrict evidence as required; reproducibility does not permit leaking private data.
- Keep earlier run generations immutable and record each change and its rationale. Distinguish observed facts from hypotheses and agent proposals from owner-approved decisions.

## 3. Diagnose surprising or poor results before rejecting

Inspect failing cases and traces, not just an aggregate score. Check:

1. Missing requester/task context, ambiguous labels or instructions, and unequal context between arms.
2. Parser/schema mismatches, output truncation/finish reasons, token budgets, and unsupported settings.
3. Tool/integration errors, stale state, upstream retrieval failures, and other confounds.
4. Whether a no-verdict becomes fail-open, fail-closed, fallback, clarification, or retry—and what the user actually experiences.

An initial result describes **the tested setup**, not intrinsic capability. Do not name a cause until an intervention or direct evidence distinguishes it from alternatives; if several things changed, report the confound.

Choose a bounded diagnostic next test: restore missing context, repair an integration, adjust an inadequate output cap, or clarify a prompt, as the evidence warrants. Retain the original result. Targeted tuning reruns are diagnostic/development evidence, **not held-out validation**.

Do not turn this into endless tuning. Prioritize tests by likely information gained and remaining authorized resources. When the budget is exhausted or further tests have low expected value, stop spending, preserve uncertainty, and explain what additional test would resolve it. A resource stop is not a capability verdict.

## 4. Assess reliability, tradeoffs, and uncertainty

- Report valid judgments and no-verdicts separately, then assess effective end-to-end results with the real fallback/retry policy. Do not drop failed attempts from denominators or count fail-open/no-verdict as a correct judgment. State denominators, exclusions, and definitions.
- Inspect paired per-case changes and important slices as well as aggregates. Identify regressions, their severity, and who bears them. Averages can hide safety failures or gains in reliability and experience.
- Repeat where nondeterminism could change the decision; report variation, uncertainty, and limitations without inventing universal sample-size or significance requirements. Avoid claiming a production error rate from a small or synthetic suite.
- Validate LLM judges against trusted/human-reviewed cases, especially disagreements and boundaries. Check rubric fit, judge bias, order sensitivity where relevant, and agreement; judge scores are evidence, not assumed ground truth. Do not calibrate and validate on the same examples without disclosing it.
- Compare practical gains and losses in quality, safety, availability, latency, cost, flexibility, and user effort. A tradeoff can be an overall plus without strict dominance; it does not excuse violating an explicit safety constraint. Report the tradeoff and recommend, but do not invent owner acceptance.

## 5. Confirm a developed hypothesis, then recommend

Once the question and proposed decision are understood, state the hypothesis, relevant criteria, and confirmation plan before running confirmation tests. Seek owner agreement where a consequential tradeoff needs their decision; do not call agent-proposed criteria approved.

Use fresh or held-out representative cases for confirmation when available. Cases used for prompt/threshold selection remain development evidence. Version the confirmation setup; if learning prompts another revision, retain the result and return to exploration transparently rather than silently moving the goalposts. A request for a narrow pre-specified benchmark can be run as given, without pretending it settles broader suitability.

Conclude with:

- **Observations:** what was tested, against which baseline, and the measured results with evidence links.
- **Causes:** what is established, what is hypothesized, and which confounds remain.
- **Tradeoffs:** practical wins, losses, per-slice risks, uncertainty, and resource use/liability.
- **Open questions and next test:** the smallest informative next step, or why none is currently justified.
- **Recommendation:** scope it to the evidence; distinguish diagnostic failure, promotion readiness, and continued investigation. Name any owner decision or authorization needed. Do not ship on evaluation authority alone.

Read [illustrative scenarios](reference/illustrative-scenarios.md) for generic examples of these methods. They are hypothetical teaching aids, not measured evidence or claims about any model or application.
