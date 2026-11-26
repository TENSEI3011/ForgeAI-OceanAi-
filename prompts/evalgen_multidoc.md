You write test questions that need information from TWO different documents. Users: {{audience}}.

Passage A (from "{{source_a}}"):
---
{{passage_a}}
---

Passage B (from "{{source_b}}"):
---
{{passage_b}}
---

Write ONE realistic user question that can only be answered completely by combining a fact from
passage A with a fact from passage B (for example a rule in one and a related limit, item, contact
or exception in the other). Never mention "passage A/B" or "the document".
The passages may describe DIFFERENT organisations, products or cases. Keep every fact attached to its
own subject: if the question compares two subjects, name both explicitly; never ask about one subject
while expecting a fact that belongs to the other.

List 2-4 expected facts, at least one from each passage. For each fact:
- "fact": 2-10 words, numbers and names copied exactly
- "passage": "A" or "B"
- "quote": the sentence from that passage stating it, copied word for word

Return JSON:
{"question": "...", "facts": [{"fact": "...", "passage": "A", "quote": "..."}, {"fact": "...", "passage": "B", "quote": "..."}]}
