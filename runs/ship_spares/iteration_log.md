# Iteration log

**Stop reason:** dev pass rate 94% reached the target (90%)

## Iteration 1: v1 -> v2 (kept)

- Targeted categories: prompt_defect
- Overall pass rate: 83% -> 88%; dev: 83% -> 89%; holdout 83% -> 83%
- Targeted failures that now pass: E01, M02, M04
- Previously passing cases that now fail: E02, M01

### [prompt_defect] added a completeness rule (answer every part, cite each)

Why: the retrieved context contained the expected facts but answers left some out

Failures addressed: E01, M02, M04

```diff
--- domain rules (before)
+++ domain rules (after)
@@ -6 +6,2 @@
 If a supplier's terms require approval or involve a specific department, mention that requirement in your response.
+If the question has several parts or conditions, answer every part separately, giving the specific value, person or deadline the context states for each, and cite each part.
```

### [(rendered)] system prompt re-rendered from the patched spec

Why: see the changes above

Failures addressed: -

```diff
--- system prompt (before)
+++ system prompt (after)
@@ -36,2 +36,3 @@
 6. If a supplier's terms require approval or involve a specific department, mention that requirement in your response.
+7. If the question has several parts or conditions, answer every part separately, giving the specific value, person or deadline the context states for each, and cite each part.
 
```

## Iteration 2: v2 -> v3 (kept)

- Targeted categories: hallucination, prompt_defect
- Overall pass rate: 88% -> 92%; dev: 89% -> 94%; holdout 83% -> 83%
- Targeted failures that now pass: E02, M01
- Previously passing cases that now fail: E04

### [hallucination] added strict number-grounding rule; temperature 0.2 -> 0.0

Why: answers contained figures or claims that are not in the retrieved context

Failures addressed: E02

```diff
--- rules/config (before)
+++ rules/config (after)
@@ -7,2 +7,3 @@
 If the question has several parts or conditions, answer every part separately, giving the specific value, person or deadline the context states for each, and cite each part.
-temperature=0.2 min_score=0.2
+Before writing any number, amount, date or code, find it in the context passages or tool results; if it is not there, do not write it.
+temperature=0.0 min_score=0.2
```

### [prompt_defect] added rule; rejected 1 leaking/invalid rule(s)

Why: This ensures that when a threshold definition exists in the context, the associated consequence is captured and reported, preventing omissions in comparative responses even when the query structure is indirect.

Failures addressed: M01

```diff
--- domain rules (before)
+++ domain rules (after)
@@ -8 +8,2 @@
 Before writing any number, amount, date or code, find it in the context passages or tool results; if it is not there, do not write it.
+When comparing categories defined by thresholds (e.g., lead time, packaging status), explicitly state the definition and example from the source if provided, even if the full policy is not cited.
```

### [(rendered)] system prompt re-rendered from the patched spec

Why: see the changes above

Failures addressed: -

```diff
--- system prompt (before)
+++ system prompt (after)
@@ -37,2 +37,4 @@
 7. If the question has several parts or conditions, answer every part separately, giving the specific value, person or deadline the context states for each, and cite each part.
+8. Before writing any number, amount, date or code, find it in the context passages or tool results; if it is not there, do not write it.
+9. When comparing categories defined by thresholds (e.g., lead time, packaging status), explicitly state the definition and example from the source if provided, even if the full policy is not cited.
 
```

## Rejected patch rules (leak guard / validation)

- (prompt_defect) `If a condition or threshold is defined in a document (e.g., lead time over 30 days, opened packaging), and the consequence (e.g., no return, restocking fee)...`: may not rewrite an optimizer safety rule
