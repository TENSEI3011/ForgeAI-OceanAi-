You maintain the system prompt of a document-grounded assistant. Some test answers failed.
Propose the SMALLEST rule change that fixes this class of failure in general.

Problem observed: {{problem}}

The assistant's role:
{{role}}

Its current domain rules (index. text):
{{rules}}

(Grounding, citation and refusal rules already exist separately and cannot be changed here.)

Failing examples:
{{examples}}

Rules that were already tried and did NOT improve the results (do not propose them again; try a
different angle):
{{previous}}

Write general rules, not answers:
- NEVER put specific facts, numbers, names, codes or the example questions into a rule. Rules must
  work for any future question. A rule that contains an answer will be rejected automatically.
- Prefer clarifying or modifying an existing rule (modify_rules) over adding new ones.
- At most 2 changes in total.

Return JSON:
{"add_rules": ["..."], "modify_rules": [{"index": 0, "new_text": "..."}], "rationale": "one sentence"}
