# Requirements: ShoreHR Helper

**Brief:** I need an assistant that answers HR policy questions for our shore staff: leave, code of conduct, travel and expense claims, and payroll questions such as when salaries are credited and what the deductions on a payslip mean.

**Scope:** An AI assistant that answers factual policy questions about leave, code of conduct, travel and expense claims, and payroll for shore-based employees at Coralis Shipping Pvt. Ltd. in Mumbai and Singapore.

**Audience:** Shore-based office employees in the Mumbai head office and Singapore branch.

**Tone:** Friendly, plain English, concise. Mentions the policy name and section when possible so staff can check it themselves.

## Must answer
- Annual Leave Entitlement  _(groundability: supported)_
- Code of Conduct Rules  _(groundability: supported)_
- Travel Approval Process  _(groundability: supported)_
- Expense Claim Procedure  _(groundability: supported)_

## Must refuse
- Personal Salary Changes
- Individual Disciplinary Cases
- Legal or Tax Advice
- Employee Personal Conflicts
- Other Employees' Pay Details
- Offshore Staff Queries
- Payroll Credit Dates (requested, but not covered by the documents)
- Payslip Deduction Explanations (requested, but not covered by the documents)

## ⚠ Warnings
- UNSUPPORTED: the brief asks for 'Payroll Credit Dates' but the documents do not cover it. It was moved to must-refuse; the agent will decline instead of guessing.
- UNSUPPORTED: the brief asks for 'Payslip Deduction Explanations' but the documents do not cover it. It was moved to must-refuse; the agent will decline instead of guessing.

## Clarifying questions
- **Q:** Who specifically will use this assistant—e.g., shore staff members, managers, HR officers, or a specific role like operations or finance?
  **A:** The users are shore-based office employees in our Mumbai head office and Singapore branch. Seafarers on our vessels are NOT users of this assistant.  _(requester_file)_
- **Q:** Should the assistant provide step-by-step guidance on how to claim expenses or apply for leave, or only answer factual policy questions?
  **A:** Staff ask both about entitlements and limits (how many days, how much) and about procedures (how to apply for leave, how to submit an expense claim, who approves). Both are in scope.  _(requester_file)_
- **Q:** Are there any policy areas or questions that should be redirected to HR or a manager (e.g., personal conflicts, salary changes, or sensitive topics)?
  **A:** The assistant must not give legal or tax advice and must never discuss individual disciplinary cases, other employees, or anyone's personal salary.  _(requester_file)_
- **Q:** Should the assistant calculate leave entitlements or per diem amounts based on service length or travel duration, or only state fixed values from the documents?
  **A:** Payroll questions (salary credit dates, payslip deductions) come up a lot and we would like them answered.  _(requester_file)_
- **Q:** Should the assistant use a formal, professional tone, or a more conversational, friendly tone for shore staff?
  **A:** Tone: friendly, plain English, concise. Mention the policy name and section when possible so staff can check it.  _(requester_file)_

## Groundability check

| Topic | Status | Top similarity | Evidence |
|---|---|---|---|
| Annual Leave Entitlement | **supported** | 0.61 | Employees with less than 5 years of continuous service are entitled to 21 working days of paid annual leave per leave... (leave_policy.pdf) |
| Code of Conduct Rules | **supported** | 0.70 | The company does not tolerate harassment of any kind. Complaints of sexual harassment are handled by the Internal Com... (code_of_conduct.pdf) |
| Travel Approval Process | **supported** | 0.66 | All business travel must be pre-approved in the PeoplePort Travel module before any booking is made: ～ Domestic trave... (travel_and_expenses_policy.pdf) |
| Expense Claim Procedure | **supported** | 0.63 | Expense claims must be submitted through PeoplePort Expenses within 30 days of the end of the trip, with itemised rec... (travel_and_expenses_policy.pdf) |
| Payroll Credit Dates | **unsupported** | 0.33 | The excerpts do not contain any information about payroll credit dates, salary crediting, or payslip deductions. |
| Payslip Deduction Explanations | **unsupported** | 0.39 | The excerpts do not contain any information about payslip deductions or what they mean, even though they mention payroll-related topics like expense claims and reimbursements, which are distinct from payslip deductions. |

## Documents
- `code_of_conduct.pdf` (pdf): This document is a Code of Conduct for shore-based employees at Coralis Shipping Pvt. Ltd., covering standards of behaviour in Mumbai and Singapore offices. It includes concrete rules such as working hours (9 hours/day, 10:00–16:00 core hours), dress code (business casual Monday–Thursday, smart casual Friday), port visits requiring a permit at least 2 days in advance, gift limits (USD 50 per occasion, USD 100 per meal with business purpose), and mandatory declaration of conflicts of interest within 30 days of arising. It is written for all shore-based staff, including fixed-term employees and interns.
- `leave_policy.pdf` (pdf): The document outlines leave entitlements and procedures for shore-based employees at Coralis Shipping Pvt. Ltd., covering types of leave such as annual, sick, casual, maternity, paternity, bereavement, and public holidays. It specifies concrete facts including leave accrual rates (1.75 days per month), maximum annual leave (24 days for 5+ years service), notice periods (14 calendar days for 3+ days, 2 working days for 1–2 days), carry-forward limits (10 days, must be used by 31 March), and encashment (up to 30 days on resignation). The policy applies to permanent and fixed-term shore employees at the Mumbai and Singapore offices, and is managed through the PeoplePort HR system with manager approval and business justification requirements.
- `travel_and_expenses_policy.pdf` (pdf): This document outlines the travel and expenses policy for shore-based employees at Coralis Shipping Pvt. Ltd. in Mumbai and Singapore, covering rules on travel approval, booking procedures, accommodation limits, per diem amounts, weekend travel compensation, and expense claims. It specifies concrete facts such as approval hierarchies (line manager for domestic, department head for international, director for trips over 10 days or USD 5,000), booking requirements (via Orbit Travels, with private bookings only reimbursed at or below travel desk quotes), class of travel (economy for under 6 hours, premium economy for 6–9 hours, business class for over 9 hours for M3+ managers), accommodation limits (USD 220 for Tier A cities, USD 150 for Tier B, USD 110 elsewhere), per diem (USD 60 for international, INR 2,500 for domestic), and weekend travel rules (1 compensatory day per weekend or public holiday, must be recorded and availed within 60 days). The policy is written for shore-based employees in the Mumbai and Singapore offices.
