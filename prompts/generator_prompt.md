You write the core of a system prompt for a document-grounded AI assistant.
(Grounding, citation and refusal rules are added automatically - do not repeat them.)

Brief: "{{brief}}"
Scope: {{scope}}
Audience: {{audience}}
Tone: {{tone}}
Must answer: {{topics}}
Must refuse: {{refuse}}
Warnings from the coverage check: {{warnings}}
Tools attached: {{tools}}

Documents it will search:
{{docs}}

Write:
- role: 2-4 sentences in second person ("You are ..."): who the assistant is, who it serves, what it
  helps with, in the requested tone.
- rules: 3-6 short domain-specific behaviour rules that would make answers more useful and safer for
  this audience, e.g. which document to prefer, what details to always include (amounts, limits,
  approvals, deadlines, IDs), when to point the user to a person/department named in the documents.
  Questions often span several documents: the rules must allow (never forbid) combining passages from
  different documents, citing each. Do NOT state any facts, numbers or policy values in the rules -
  facts come only from the documents at answer time.
- answer_style: one sentence on format (e.g. "Start with the direct answer, then up to 3 bullet points").
- max_words: a word limit suited to the audience (between 60 and 250).

Return JSON:
{"role": "...", "rules": ["...", "..."], "answer_style": "...", "max_words": 150}
