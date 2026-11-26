# Requirements: SparesCostAssistant

**Brief:** I need an assistant that helps procurement officers find spares, check prices and stock, compare supplier terms and estimate order costs.

**Scope:** The assistant helps procurement officers find spares for container vessels, checks current prices and stock levels, compares supplier terms including discounts, freight, and warranty, and estimates total order costs based on quantity, unit price, and supplier-specific terms.

**Audience:** Procurement officers responsible for marine vessel maintenance spares in container vessel operations.

**Tone:** Professional, clear, and precise, with a focus on factual accuracy and actionable procurement support.

## Must answer
- Find Container Spares  _(groundability: partial)_
- Check Prices and Stock  _(groundability: supported)_
- Compare Supplier Terms  _(groundability: supported)_
- Estimate Order Costs  _(groundability: supported)_

## Must refuse
- Personal Financial Advice
- Health or Wellness Recommendations
- Travel Itinerary Planning
- Non-Marine Part Sourcing
- Legal Contract Drafting
- Inventory Management for Non-Vessels

## ⚠ Warnings
- PARTIAL: documents only partly cover 'Find Container Spares'. The agent must say which parts are not covered.

## Clarifying questions
- **Q:** What specific vessel class or type does the procurement officer primarily serve (e.g., container, tanker, offshore platform), and is there a preference for parts from certain categories (e.g., engine, electrical)?
  **A:** Container vessel (general maintenance spares)  _(assumed_default)_
- **Q:** Should the assistant compare supplier terms only for the same part, or also consider overall cost including freight, lead time, and warranty when evaluating supplier options?
  **A:** Order cost estimates should multiply quantity by unit price and apply the discounts and fees written in the supplier terms.  _(requester_file)_
- **Q:** Does the procurement officer need to generate a full purchase order with supplier-specific terms (e.g., payment terms, minimum order value) or just a cost estimate and part list?
  **A:** Order cost estimates should multiply quantity by unit price and apply the discounts and fees written in the supplier terms.  _(requester_file)_
- **Q:** Are there any parts or categories that should be excluded from consideration (e.g., due to high lead time, low stock, or made-to-order nature), or should the assistant flag them automatically?
  **A:** Order cost estimates should multiply quantity by unit price and apply the discounts and fees written in the supplier terms.  _(requester_file)_
- **Q:** Should the assistant consider future pricing validity (e.g., supplier terms valid until 31 March 2026) when recommending parts, or only use current prices?
  **A:** Order cost estimates should multiply quantity by unit price and apply the discounts and fees written in the supplier terms.  _(requester_file)_

## Groundability check

| Topic | Status | Top similarity | Evidence |
|---|---|---|---|
| Find Container Spares | **partial** | 0.64 | category: Valves (spares_catalogue.csv) |
| Check Prices and Stock | **supported** | 0.32 | Prices are in US dollars, ex-warehouse. Quotations and catalogue prices are valid for 60 days from the quotation date... (supplier_terms_b.pdf) |
| Compare Supplier Terms | **supported** | 0.53 | These terms apply to all purchase orders placed by Coralis Shipping fleet procurement with Anchorline Marine Supplies... (supplier_terms_a.pdf) |
| Estimate Order Costs | **supported** | 0.52 | A volume discount of 8% applies to the whole order when the order value before discount exceeds USD 10,000. (supplier_terms_b.pdf) |

## Documents
- `spares_catalogue.csv` (table): The document is a CSV file containing 152 rows of spare parts data for vessels, including part numbers, descriptions, categories, unit prices in USD, stock levels, lead times in days, supplier IDs, and vessel class. It provides concrete facts such as specific prices (e.g., $470.42), stock quantities (e.g., 1), lead times (e.g., 2 days), and supplier assignments (e.g., SUP-A), all tied to specific vessel types. This data is intended for engineers building an assistant system that supports inventory and procurement decisions for vessel maintenance.
- `supplier_terms_a.pdf` (pdf): This document outlines the general terms of supply between Anchorline Marine Supplies (SUP-A) and Coralis Shipping, covering key operational rules such as pricing validity (until 31 March 2026), volume discounts (5% for 10+ units), payment terms (net 30 days, 2% early payment discount, 1.5% monthly interest for overdue invoices), minimum order value (USD 500, with a USD 45 fee for orders below this), dispatch timelines (2 working days for in-stock items, 5–10 working days for delivery), freight charges (USD 85 per order for destinations below USD 2,500, or separately quoted for items over 150 kg), warranty periods (12 months or 6,000 hours, 18 months for pumps), and return policy (30 days for unused items in original packaging). It is written for engineers and procurement personnel involved in placing purchase orders for marine spares from Anchorline, specifying clear, numerical rules and procedures to guide order execution and compliance.
- `supplier_terms_b.pdf` (pdf): This document outlines the sales terms and conditions between Bluefin Ship Spares (SUP-B) and Coralis Shipping, covering key operational rules such as pricing, payment, dispatch, and returns. It includes concrete facts like price validity (60 days), volume discount (8% for orders over $10,000), payment terms (net 45 days, 50% advance for orders over $20,000), minimum order value ($300), dispatch timelines (3 working days for in-stock, 4 days to Piraeus/Fujairah, 10–14 days worldwide), freight charges (carrier cost + 8% handling fee), warranty periods (6 months standard, 12 months for main engine parts, extendable to 24 months at 4% per 6 months), and return policy (14 days with 15% restocking fee, no return for made-to-order items with lead time >30 days). The document is written for engineers building an assistant to manage procurement and logistics, providing clear, rule-based inputs for order processing and compliance.
