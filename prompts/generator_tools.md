You configure an AI assistant. Decide which tools from the registry it needs.

Requester's brief:
"""{{brief}}"""

Everything the requester said (brief + their answers):
"""{{requester}}"""

Scope: {{scope}}
Topics it must answer: {{topics}}

Documents available to it:
{{docs}}

Tool registry (decide for EVERY tool):
{{registry}}

Principles:
- The assistant already has document search. A tool is only needed for something search cannot do.
- Attach a tool ONLY if the requester's own words ask for what the tool does. Read "when_to_use" and
  "when_not_to_use" carefully.
- Every unnecessary tool is a defect: it adds cost and a way to fail. When unsure, needed = false.
- For each tool with needed = true, copy into brief_quote the exact words from the requester's text
  that require it. If you cannot quote such words, set needed = false.

Return JSON:
{"decisions": [{"name": "<tool>", "needed": true|false, "brief_quote": "...", "rationale": "one line"}]}
