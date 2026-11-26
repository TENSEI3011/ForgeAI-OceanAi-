"""The tool registry: the closed set of tools a generated agent may be given.

The generator chooses tools by reading `description`, `when_to_use` and `when_not_to_use`.
Nothing here mentions any specific business domain: tool choice must come from the brief.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from . import calculator, csv_lookup, current_date, weather


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    when_to_use: str
    when_not_to_use: str
    params: dict[str, str]
    fn: Callable[[dict[str, Any], dict[str, Any]], str]
    requires_tables: bool = False   # precondition checked in code, not by the LLM


TOOLS: dict[str, ToolSpec] = {
    "csv_lookup": ToolSpec(
        name="csv_lookup",
        description="Exact lookup/filter on structured tabular data (catalogues, price lists, inventories, "
                    "part or item numbers) stored as CSV files in the document folder.",
        when_to_use="The requester wants users to look up, filter or compare specific rows/records/items "
                    "(e.g. by ID, code, name, price, quantity) AND the documents include CSV tables.",
        when_not_to_use="The documents are only prose (policies, manuals, FAQs) or the requester only needs "
                        "explanations of rules; semantic search already covers prose.",
        params={"file": "CSV file name", "column": "column to match",
                "value": "value to match", "match": "equals | contains | lt | gt"},
        fn=csv_lookup.run,
        requires_tables=True,
    ),
    "calculator": ToolSpec(
        name="calculator",
        description="Safe arithmetic on numbers (totals, sums, percentages, discounts, quantity x price).",
        when_to_use="The requester explicitly expects the assistant to compute numbers: estimate costs, "
                    "totals, quantities, discounts, budgets or other arithmetic results.",
        when_not_to_use="Users only ask what a rule or document says, even if the answer contains numbers "
                        "(stating '21 days' or 'USD 50' requires no arithmetic).",
        params={"expression": "arithmetic expression, e.g. 12 * 45.5 * (1 - 0.05)"},
        fn=calculator.run,
    ),
    "weather": ToolSpec(
        name="weather",
        description="Live current weather and 3-day forecast for a named place or coordinates (Open-Meteo).",
        when_to_use="The requester explicitly mentions weather, wind, sea or forecast conditions for "
                    "locations as something the assistant must report.",
        when_not_to_use="Anything else. Weather is never implied by policies, catalogues, prices, "
                        "people or procedures. Attaching it without an explicit weather need is a defect.",
        params={"location": "place name (or latitude + longitude)"},
        fn=weather.run,
    ),
    "current_date": ToolSpec(
        name="current_date",
        description="Today's date and weekday from the system clock.",
        when_to_use="The requester expects answers that depend on today's date: days remaining, deadlines, "
                    "due dates, expiry, ages of items, 'how long until' or 'is it overdue' questions.",
        when_not_to_use="Questions about fixed rules or durations that do not depend on what day it is "
                        "today (e.g. 'how many days does the approval process take').",
        params={},
        fn=current_date.run,
    ),
}


def registry_for_prompt() -> list[dict[str, Any]]:
    """The registry as plain data for the generator prompt."""
    return [{"name": t.name, "description": t.description, "when_to_use": t.when_to_use,
             "when_not_to_use": t.when_not_to_use} for t in TOOLS.values()]


def run_tool(name: str, args: dict[str, Any], ctx: dict[str, Any], allowed: list[str]) -> tuple[str, bool]:
    """Execute a tool. Only tools attached to the agent definition may run."""
    if name not in allowed:
        return f"ERROR: tool '{name}' is not available to this agent", False
    if name not in TOOLS:
        return f"ERROR: unknown tool '{name}'", False
    try:
        return TOOLS[name].fn(args or {}, ctx), True
    except Exception as exc:  # tool errors are reported to the model, never raised
        return f"ERROR: {type(exc).__name__}: {exc}", False
