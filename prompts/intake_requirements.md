Write the requirements for an AI assistant from the requester's brief and their answers.

Brief:
"""{{brief}}"""

What the brief asks for (each item MUST be covered by a must-answer topic):
{{demands}}

Clarifying questions and answers:
{{qa}}

Available documents (for context only - do NOT derive topics from their table of contents):
{{docs}}

Fill in:
- agent_name: short descriptive name (2-5 words).
- scope: one or two sentences on what the assistant does.
- audience: who will use it.
- tone: how it should sound (from the answers if given).
- must_answer_topics: 3-8 BROAD topic names (2-6 words each), one per subject area the requester asked
  for (from the brief items above and the answers). Keep a requested topic even if no document seems to
  cover it - a separate check verifies coverage later. Do not split one area into many sub-topics, and
  do not add areas the requester never asked for.
- must_refuse_topics: 2-6 short topic names the assistant must decline: topics the requester said to
  refuse, plus clearly out-of-scope areas for this audience (e.g. personal advice, unrelated subjects).

Return JSON:
{"agent_name": "...", "scope": "...", "audience": "...", "tone": "...",
 "must_answer_topics": ["..."], "must_refuse_topics": ["..."]}
