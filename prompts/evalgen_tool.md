You write a test question that requires ARITHMETIC on numbers from a document. Users: {{audience}}.

Passage from "{{source}}":
---
{{passage}}
---

Write ONE realistic question whose answer needs a calculation using numbers from this passage
(for example a quantity times a unit price, a total, a difference, or a percentage of an amount).
You may introduce one small quantity in the question (e.g. "for 4 units").

Return:
- "question": the user question (do not include the final result)
- "expression": the arithmetic expression that computes the answer, using only numbers from the passage
  and the question, e.g. "4 * 120.50"
- "quote": the sentence or table text from the passage containing the input numbers, word for word
- "fact": the final answer as a short phrase containing the computed number

Return JSON:
{"question": "...", "expression": "...", "quote": "...", "fact": "..."}
