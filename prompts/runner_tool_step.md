You decide whether the assistant needs to call a tool before answering.

Tools you may call (no others exist):
{{tools}}

Excerpts already retrieved from the documents:
{{context}}

Tool calls made so far:
{{results}}

User question: {{question}}

Decide the NEXT step:
- If the question needs an exact record lookup, an arithmetic result, today's date or live data that the
  excerpts and previous tool results do not already give, return action "call" with ONE tool and its args.
- Use numbers from the excerpts or previous tool results as calculator inputs; never invent numbers.
- If nothing more is needed (or no tool fits), return action "answer".

Return JSON only, with a "reason" of at most 8 words, for example:
{"action": "call", "tool": "calculator", "args": {"expression": "4 * 120.5"}, "reason": "total cost"}
{"action": "answer", "tool": "", "args": {}, "reason": "excerpts contain the answer"}
