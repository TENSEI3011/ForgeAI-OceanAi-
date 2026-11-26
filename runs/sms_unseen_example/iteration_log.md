# Iteration log

**Stop reason:** reached the maximum of 3 iterations

## Iteration 1: v1 -> v2 (reverted: no improvement)

- Targeted categories: prompt_defect, wrong_refusal
- Overall pass rate: 90% -> 90%; dev: 87% -> 87%; holdout 100% -> 100%
- Targeted failures that now pass: O04
- Previously passing cases that now fail: E04

### [prompt_defect] added a completeness rule (answer every part, cite each)

Why: the retrieved context contained the expected facts but answers left some out

Failures addressed: A08

```diff
--- domain rules (before)
+++ domain rules (after)
@@ -6 +6,2 @@
 Do not infer or assume values not explicitly stated in the documents
+If the question has several parts or conditions, answer every part separately, giving the specific value, person or deadline the context states for each, and cite each part.
```

### [wrong_refusal] added 1 generalised refuse topic(s) and an explicit scope rule

Why: the agent answered questions it should have declined (over-answering)

Failures addressed: O04

```diff
--- refuse topics (before)
+++ refuse topics (after)
@@ -6 +6,2 @@
 Non-Safety System Queries
+emergency procedure response
```

### [(rendered)] system prompt re-rendered from the patched spec

Why: see the changes above

Failures addressed: -

```diff
--- system prompt (before)
+++ system prompt (after)
@@ -22,2 +22,3 @@
 - Non-Safety System Queries
+- emergency procedure response
 - Anything the provided documents do not support.
@@ -39,2 +40,4 @@
 6. Do not infer or assume values not explicitly stated in the documents
+7. If the question has several parts or conditions, answer every part separately, giving the specific value, person or deadline the context states for each, and cite each part.
+8. Decline any question whose subject is not listed under 'What you answer', even if the context contains loosely related words.
 
```

## Iteration 2: v1 -> v3 (reverted: no improvement)

- Targeted categories: prompt_defect
- Overall pass rate: 90% -> 90%; dev: 87% -> 87%; holdout 100% -> 100%
- Targeted failures that now pass: none
- Previously passing cases that now fail: E04

### [prompt_defect] modified rule 2, added rule

Why: This ensures that when multiple values exist for the same category in different documents, all are captured and presented, preventing omission of required facts even when the context is present.

Failures addressed: A08

```diff
--- domain rules (before)
+++ domain rules (after)
@@ -2,3 +2,3 @@
 Combine relevant facts from multiple documents when answering complex questions
-Include all required details such as deadlines, forms, and responsibilities as stated in the documents
+Include all required details such as deadlines, forms, and responsibilities as stated in the documents, and if multiple values are provided for the same category (e.g., different permit types), list all of them explicitly.
 If a document does not specify a value, state that the information is not available in the current documentation
@@ -6 +6,2 @@
 Do not infer or assume values not explicitly stated in the documents
+When a question asks for a value that is explicitly stated in multiple documents, combine the values from all relevant documents and list them all, even if they pertain to different types of permits or procedures.
```

### [(rendered)] system prompt re-rendered from the patched spec

Why: see the changes above

Failures addressed: -

```diff
--- system prompt (before)
+++ system prompt (after)
@@ -35,3 +35,3 @@
 2. Combine relevant facts from multiple documents when answering complex questions
-3. Include all required details such as deadlines, forms, and responsibilities as stated in the documents
+3. Include all required details such as deadlines, forms, and responsibilities as stated in the documents, and if multiple values are provided for the same category (e.g., different permit types), list all of them explicitly.
 4. If a document does not specify a value, state that the information is not available in the current documentation
@@ -39,2 +39,3 @@
 6. Do not infer or assume values not explicitly stated in the documents
+7. When a question asks for a value that is explicitly stated in multiple documents, combine the values from all relevant documents and list them all, even if they pertain to different types of permits or procedures.
 
```

## Iteration 3: v1 -> v4 (reverted: no improvement)

- Targeted categories: prompt_defect
- Overall pass rate: 90% -> 90%; dev: 87% -> 87%; holdout 100% -> 100%
- Targeted failures that now pass: none
- Previously passing cases that now fail: E04

### [prompt_defect] modified rule 2, added rule

Why: This ensures that when multiple values exist for the same category in a single document, they are all captured and cited, preventing omission of required facts even when the context is present.

Failures addressed: A08

```diff
--- domain rules (before)
+++ domain rules (after)
@@ -2,3 +2,3 @@
 Combine relevant facts from multiple documents when answering complex questions
-Include all required details such as deadlines, forms, and responsibilities as stated in the documents
+Include all required details such as deadlines, forms, and responsibilities as stated in the documents, and if multiple values are provided for the same category (e.g., different permit types), list all of them explicitly and cite each with its specific context.
 If a document does not specify a value, state that the information is not available in the current documentation
@@ -6 +6,2 @@
 Do not infer or assume values not explicitly stated in the documents
+When a question asks for a value that is explicitly stated in multiple related sections of the same document, list all such values even if they pertain to different permit types or procedures, and cite each value with its specific context.
```

### [(rendered)] system prompt re-rendered from the patched spec

Why: see the changes above

Failures addressed: -

```diff
--- system prompt (before)
+++ system prompt (after)
@@ -35,3 +35,3 @@
 2. Combine relevant facts from multiple documents when answering complex questions
-3. Include all required details such as deadlines, forms, and responsibilities as stated in the documents
+3. Include all required details such as deadlines, forms, and responsibilities as stated in the documents, and if multiple values are provided for the same category (e.g., different permit types), list all of them explicitly and cite each with its specific context.
 4. If a document does not specify a value, state that the information is not available in the current documentation
@@ -39,2 +39,3 @@
 6. Do not infer or assume values not explicitly stated in the documents
+7. When a question asks for a value that is explicitly stated in multiple related sections of the same document, list all such values even if they pertain to different permit types or procedures, and cite each value with its specific context.
 
```

