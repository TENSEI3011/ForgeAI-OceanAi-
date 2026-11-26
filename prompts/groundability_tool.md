The documents cannot support this requested topic: "{{topic}}"
(Brief: "{{brief}}")

Could one of these tools provide it instead? Tools give live data, today's date, arithmetic or exact
table lookups; they do NOT contain policies, procedures or other written knowledge.

{{registry}}

Name a tool ONLY if the topic is essentially "get live data / today's date / a calculation / a table
lookup" that the tool does by itself. If the topic needs written knowledge, return an empty tool.
Examples: "when is X paid / what is the rule for X" needs written knowledge (no tool), even though it
mentions dates or money. "How many days until a date" is a date calculation. "Current conditions at a
place" is live data.

Return JSON: {"tool": "<tool name or empty>", "reason": "one short sentence"}
