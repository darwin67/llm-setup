# Illustrative scenarios

These independently constructed, hypothetical scenarios teach evaluation methods. They are not measured evidence, reports of real events, or claims about particular models, providers, organizations, or applications. No numerical results or acceptance thresholds are implied.

## An invented requirement hides a useful tradeoff

Suppose a writing assistant produces more useful edits with a candidate configuration, but takes longer to respond. An evaluator decides that any latency regression disqualifies it, even though the owner has not required that tradeoff. A competing configuration responds quickly but requires more manual correction.

**Better investigation:** Compare the deployed baseline and the candidates on useful output, response time, and total user effort. Identify the proposed latency bar as an evaluator assumption, not an approved requirement. Investigate whether the delay is noticeable and whether reduced correction work offsets it. Recommend a tradeoff without claiming the owner has accepted it.

**Lesson:** A failed provisional criterion, promotion readiness, and whether further investigation is worthwhile are different questions. Improvement on every metric is not an automatic requirement.

## An apparent reasoning failure is an information gap

Suppose an assistant transforms a table but misinterprets a column. The evaluation prompt includes values and abbreviated headings, while the definition of the column exists only in a separate data dictionary. Repeating the same incomplete prompt produces inconsistent interpretations.

**Better investigation:** Inspect the actual serialized input and the reference answer. Supply the missing definition in a versioned diagnostic run while keeping other variables controlled. If formatting or instructions also change, disclose that the intervention does not isolate the definition alone. Retain the original failure and use fresh cases before making broader claims.

**Lesson:** Variation is observable without proving an intrinsic capability limit. Check whether the task is answerable from the supplied information before blaming the model or adjusting a scoring threshold.

## Valid-looking averages hide unavailable answers

Suppose an assistant must produce a multi-part structured response. The output allowance was chosen for a much shorter response, so some attempts end before the final fields. A dashboard reports quality only among parseable responses, while the application silently falls back to a generic answer on the others.

**Better investigation:** Separate valid judgments, incomplete outputs, parser failures, and fallback outcomes. Compare effective user results across all attempts. Within the authorized resource budget, test whether an appropriate output allowance resolves the incomplete responses without changing the task. Preserve both configurations and account for their costs and latency.

**Lesson:** A missing answer is not a successful model judgment, even if a fallback avoids an error. A repairable configuration failure does not prove weak task capability; fixing it on observed cases is not independent validation.

## A real negative result does not transfer to unrelated tasks

Suppose a candidate repeatedly omits important dependencies when synthesizing long documents, despite complete inputs and a working integration. Those failures may justify recommending against that tested use. A separate proposal concerns assigning a short text to a broad topic category.

**Better investigation:** Keep the synthesis result as valid negative evidence for its tested scope. Do not substitute it for an evaluation of short-text categorization, which has a different input, output contract, and failure cost. Choose a small representative test for the new task if the remaining authorized budget and expected information gain justify it.

**Lesson:** Neither enthusiasm nor disappointment transfers evidence across unrelated tasks. Continue only where an informative bounded test is worthwhile; stopping for resource reasons is not a capability verdict.
