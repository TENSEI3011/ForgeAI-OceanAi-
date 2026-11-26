You write test questions for an AI assistant. Users: {{audience}}. Scope: {{scope}}

Below is one passage from the document "{{source}}".
---
{{passage}}
---

Write ONE question that a real user would ask, which this passage fully answers.
- Ask about concrete details (numbers, limits, deadlines, conditions, names, IDs) rather than vague themes.
- The question must have exactly ONE correct answer. If the passage is a table row (or describes one of
  several similar items, places or organisations), name the exact item in the question (its ID/code, or
  every distinguishing value such as a variant or type), because similar records exist.
- Phrase it the way the user would ask, without copying long phrases from the passage.
- Never mention "the passage", "the text" or "the document".
- Do not put the answer in the question.

Then list 1-3 short expected facts that a correct answer must contain. For each fact:
- "fact": 2-10 words; copy numbers, units, codes and names exactly as written in the passage.
- "quote": the sentence (or table cell text) from the passage that states it, copied word for word.

Return JSON:
{"question": "...", "facts": [{"fact": "...", "quote": "..."}]}
