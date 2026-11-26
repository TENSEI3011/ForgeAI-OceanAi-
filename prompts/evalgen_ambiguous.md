You write HARD test questions for an AI assistant used by: {{audience}}.

Below is one passage from the document "{{source}}".
---
{{passage}}
---

Write ONE question whose answer is in this passage, but phrased like this:
{{style}}

The question must still have exactly one clear correct answer in the passage: if the passage is one of
several similar records (e.g. a table row), keep enough detail (an ID, variant or type, possibly
misspelled) to identify it. Never mention "the passage" or "the document", and do not put the answer in
the question.

Then list 1-3 short expected facts that a correct answer must contain. For each fact:
- "fact": 2-10 words; copy numbers, units, codes and names exactly as written in the passage.
- "quote": the sentence (or table cell text) from the passage that states it, copied word for word.

Return JSON:
{"question": "...", "facts": [{"fact": "...", "quote": "..."}]}
