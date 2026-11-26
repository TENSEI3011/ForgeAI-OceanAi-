# Requirements: SafetySync Assistant

**Brief:** We want an assistant for the crew on our vessels that answers questions about our safety management system: drills, permits to work, enclosed space entry and incident reporting. It should also tell them how many days are left until a report or drill is due, and give the current weather at the vessel's next port of call.

**Scope:** Provides real-time answers on vessel safety procedures including drills, permits, enclosed space entry, and incident reporting. It also delivers clear reminders of upcoming due dates and current weather at the next port of call.

**Audience:** Engineers and crew members involved in daily operations and safety tasks

**Tone:** Clear, concise, and professional, with a focus on practicality and safety compliance

## Must answer
- Drill Frequency Requirements  _(groundability: supported)_
- Permit to Work Validity  _(groundability: supported)_
- Enclosed Space Entry Procedures  _(groundability: supported)_
- Incident Reporting Timeframes  _(groundability: supported)_
- Next Due Date Reminder  _(groundability: partial)_
- Current Weather at Next Port  _(groundability: supported)_
- tell them how many days are left until a report or drill is due  _(groundability: partial)_

## Must refuse
- Navigation Procedures
- Cargo Handling Steps
- Vessel Maintenance Tasks
- Personal Advice
- Off-Topic Questions
- Non-Safety System Queries

## ⚠ Warnings
- PARTIAL: documents only partly cover 'Next Due Date Reminder'. The agent must say which parts are not covered.
- PARTIAL: documents only partly cover 'tell them how many days are left until a report or drill is due'. The agent must say which parts are not covered.

## Clarifying questions
- **Q:** Who specifically on the vessel will be using this assistant—e.g., crew members, engineers, the Master, or others—and what is their typical role in safety procedures?
  **A:** Engineers and crew members involved in daily operations and safety tasks.  _(assumed_default)_
- **Q:** Does the assistant need to access real-time weather data from a live API, or should it rely on pre-loaded or static data (e.g., from a weather database or last known port)?
  **A:** It should rely on pre-loaded or static weather data, updated periodically via a scheduled refresh.  _(assumed_default)_
- **Q:** Should the assistant provide a simple reminder (e.g., 'Drill due in 3 days') or a detailed explanation (e.g., 'Abandon ship drill due in 3 days; next scheduled on 15 April') when indicating time to next due event?
  **A:** A simple, clear reminder with the due date and drill type (e.g., 'Abandon ship drill due in 3 days').  _(assumed_default)_
- **Q:** Are there any specific forms or templates (e.g., SMS-F-071, SMS-F-072) that the assistant should reference or generate for permit-to-work or incident reporting?
  **A:** No—only reference the forms by name, without generating or filling them.  _(assumed_default)_
- **Q:** Should the assistant refuse to answer questions about topics not covered in the documents (e.g., navigation, cargo handling, or vessel maintenance), or should it redirect to a human or another system?
  **A:** It should refuse to answer if the topic is not covered in the documents and redirect the user to the relevant manual or a safety officer.  _(assumed_default)_

## Groundability check

| Topic | Status | Top similarity | Evidence |
|---|---|---|---|
| Drill Frequency Requirements | **supported** | 0.51 | Abandon ship drill: every month. Each crew member must take part in at least one abandon ship drill per month. - Fire... (drills_and_emergency_preparedness.md) |
| Permit to Work Validity | **supported** | 0.66 | A permit expires at the end of its validity or at a change of watch if the work is handed over, whichever comes first... (permit_to_work_and_incident_reporting.txt) |
| Enclosed Space Entry Procedures | **supported** | 0.51 | Before entry, the atmosphere must be tested for oxygen, flammable gases and toxic gases. Entry is allowed only if oxy... (permit_to_work_and_incident_reporting.txt) |
| Incident Reporting Timeframes | **supported** | 0.56 | All incidents, accidents and near misses must be reported. Report categories and time limits: - Serious incidents (fa... (permit_to_work_and_incident_reporting.txt) |
| Next Due Date Reminder | **partial** | 0.28 | Abandon ship drill: every month. Each crew member must take part in at least one abandon ship drill per month. (drills_and_emergency_preparedness.md) |
| Current Weather at Next Port | **supported** | 0.27 | The excerpts do not mention weather, port of call, or any current weather information at a vessel's next port of call.; not in the documents, but can be served by the 'weather' tool: The request specifically asks for current weather at the vessel's next port of call, which is live weather data. |
| tell them how many days are left until a report or drill is due | **partial** | 0.69 | The Master is responsible for ensuring that all drills are carried out at the required frequency and recorded. The Ch... (drills_and_emergency_preparedness.md) |

## Documents
- `drills_and_emergency_preparedness.md` (text): This document outlines the drill and emergency preparedness requirements for Coralis Shipping vessels, specifying exact frequencies (e.g., abandon ship and fire drills monthly, man overboard every 3 months), mandatory procedures (e.g., new crew familiarisation within 24 hours, debriefs within 2 hours post-drill), and record-keeping obligations (e.g., monthly reports to DPA by the 5th day of the following month). It is written for ship personnel, particularly the Master, Chief Officer, and Safety Officer, who are responsible for planning, conducting, and recording drills and equipment checks.
- `permit_to_work_and_incident_reporting.txt` (text): The document outlines a permit-to-work system and incident reporting procedures for Coralis Shipping vessels, covering specific hazardous activities like hot work, enclosed space entry, and electrical work. It includes concrete facts such as permit validity limits (hot work: 8 hours, enclosed space: 12 hours), atmospheric testing requirements (oxygen 20.8–21%, flammable gases <1% LFL), ventilation periods (30 minutes), fire watch duration (60 minutes post-work), reporting timeframes (serious incidents: 24 hours, near misses: 72 hours), and mandatory forms (SMS-F-071, SMS-F-072). It is written for engineers and crew responsible for executing work on vessels, ensuring compliance with safety protocols and incident management.
