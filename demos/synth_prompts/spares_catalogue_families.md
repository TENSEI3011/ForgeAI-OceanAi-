List 38 realistic spare-part families that a ship manager buys for a mixed fleet (bulk carriers,
container feeders, product tankers, offshore supply vessels).

For each family give: a 2-letter series prefix by category (ME main engine, AE auxiliary engine, PU pumps,
VL valves, FL filters, EL electrical, DK deck machinery, SF safety equipment, NV navigation), a short
technical description, the category name, a realistic unit price range in USD, a lead-time range in days,
and which supplier carries it (SUP-A, SUP-B, or SUP-C for a third supplier that has no terms document).

Return JSON lines: {"prefix": "...", "description": "...", "category": "...", "price": [min, max],
"lead_time": [min, max], "supplier": "SUP-A"}

(The rows themselves are expanded deterministically from these families by demos/synthesize.py with a
fixed random seed, so the catalogue is reproducible and part numbers stay consistent with the PDFs.)
