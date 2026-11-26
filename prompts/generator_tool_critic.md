You are an independent reviewer checking tool attachments for an AI assistant. Attaching a tool the
requester never asked for is a defect; removing a tool the requester explicitly asked for is also a defect.

Requester's brief:
"""{{brief}}"""

Everything the requester said:
"""{{requester}}"""

Documents the assistant will have:
{{docs}}

Proposed tools, each with the requester's words that supposedly require it:
{{tools}}

For each tool decide: do the quoted words (or other words of the requester) actually ask the assistant
to do what this tool does, given the documents above?
- needed = true if yes, even for a side feature. Copy the requester's exact words into brief_quote.
- needed = false if the words ask for something else (document search is always available for
  explaining written rules, so explaining rules does not by itself need a tool).
Judge only whether it was asked for, not whether it is a good idea.

Return JSON:
{"decisions": [{"name": "<tool>", "needed": true|false, "brief_quote": "...", "rationale": "one line"}]}
