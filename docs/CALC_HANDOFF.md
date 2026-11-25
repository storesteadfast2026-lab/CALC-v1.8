# CALC master continuity record

Path: `docs/handoff/CALC_HANDOFF.md`  
Last updated: 2026-11-17 · Time zone: Australia/Adelaide  
Purpose: enable a person or AI to continue the project from documented evidence without relying on chat history.

## Files read and evidence boundary

Only documents delivered or produced within this conversation were used. No application source code, Git repository, Docker environment, live system, raw freight exports or audio transcripts were inspected. File dates below are document dates unless described otherwise. Source labels S1–S4 identify evidence, not decisions.

| Source | File actually read | Date/version | SHA-256 of available file bytes |
|---|---|---|---|
| S1 | [APP-PLAN.md](https://chatgpt.com/library?file_id=libfile_6c163dc848e08191a1b7d3437db63061&account_id=6f21f5ab-ff3b-4044-a08a-0a68a5fd08fd) | Integrated 2026-11-17; version 10; includes current requirements, original Q1–Q48 and historical records | `71f84ff9f7eb66a4723af25199a1265951a93d3d13dbd3d21853c45c24ae8926` |
| S2 | [APP PLAN.md](https://chatgpt.com/library?file_id=libfile_6c163dc848e08191a1b7d3437db63061&account_id=6f21f5ab-ff3b-4044-a08a-0a68a5fd08fd) — originally uploaded snapshot, not the current integrated version | Original plan with 2026-11-11 review addendum; no original base version specified | `467b4aaceae6ef101b2f8d5f3f5fba44e0ca7d32f433e5560bd570daff28d35d` |
| S3 | [CALC_Fabian_Handover_v1.0_2026-11-13(2).md](https://chatgpt.com/library?file_id=libfile_619e234584888191ad7cfe557f5c7697&account_id=6f21f5ab-ff3b-4044-a08a-0a68a5fd08fd) | 2026-11-13; version 1.0 | `521523f8fbbe10c6af24df22f30c8dabefe7600aedf8c4e1aae1bea09bccabbe` |
| S4 | [CALC_APP_PLAN_Question_Analysis_2026-11-13.md](https://chatgpt.com/library?file_id=libfile_04f693bca4708191b96a2867577de998&account_id=6f21f5ab-ff3b-4044-a08a-0a68a5fd08fd) — supplied 2026-11-13 snapshot | 2026-11-13 analysis; historical snapshot, not a claim about later versions of that file | `f4c3429c7058f84d2f39d28d2e80f220d08fa02c3473bbbe9c27a4d2c0b1a7ac` |

S2's link resolves to the current file identity, now named APP-PLAN.md; its hash identifies the older snapshot actually read. S4's link may resolve to a later version; use the hash/date to distinguish the historical attachment. Hashes describe documentation bytes, **not** active operational data. S1's hash was calculated on the matching available 113,830-byte file; its current version was read in two contiguous windows.

This request also establishes documentation rules and the required source-authority hierarchy. These are direct task instructions, not retroactive evidence of missing ADRs, tests or past implementation. Missing references are listed in §7.

## 1. Current state — five-minute briefing

### Project and people

CALC is Steadfast Australia's web freight-estimating and carrier-comparison application. Rhys owns the project and makes final business decisions. Fabian develops and investigates technical source behaviour. Rhys performs iterative operational comparisons against TransLogic and real pricing. STH is the first customer for testing/enablement; the model supports other configured customers. Preserve useful existing work and Fabian's familiar calculator layout. [S1 §1, §14–15; S3 §1–4]

Scope includes customer/carrier/service setup, permissions, product/custom freight, measured pallet groups, kit expansion, carrier comparison, breakdowns, snapshots, history and estimate email. Booking, consigning, dispatch, order creation, stock reservation, inventory management, advanced packing optimisation and dynamic pricing are excluded from the initial scope. [S3 §2–11]

### What is known now

- The **web application is unused alpha**, as reported by Rhys in CALC-D20261117-11. Start fresh: no operational saved-estimate migration is required. This does not authorise deleting alpha work or evidence. The separate Excel calculator was reported working for STH; that is not an independently observed test. [S1 D11; S2 addendum D005]
- The confirmed operating model is **set and forget**: automatic updates, not necessarily daily; validated activation without routine human approval; source repair for exceptional defects; immediate notification of the operational team through a channel still to be agreed; no separate age-only warning. Microsoft Teams is not used. Retain last valid data after failed/incomplete imports. [S1 D01–D07; owner clarification 2026-11-18]
- Configure customer/carrier coverage and relevant business options. Site administrators manage customer activation and permissions. Staff see authorised cost and select configured margin options; customers see only assigned selling prices. [S1 D04, D10, D12, D15]
- Data issues support configured warning or blocking when a defined price can be calculated. Never fabricate amounts, select arbitrary first records or treat an unknown required charge as zero. Unaffected valid options continue. [S1 D05, D08–D10]
- Use kg, metres and m³; stock is informational. Full loaded pallet dimensions replace component volume; tare must not be counted twice. Kits expand into children without counting the parent. Preserve measured volume separately from cubic allowance. Default to Ex GST. [S3 §5–9]
- Estimates preserve original inputs, results, warnings, source versions and weekly Monday–Sunday validity. Viewing history does not recalculate; Create as new uses current rates. Expired prices warn. Quote/error logs have a three-month retention requirement; visible history is initially about 14 days and configurable. Other retention and purge details remain open. [S1 D13; S3 §10–11]
- Capacity planning is approximately **15 concurrent users**. No verified throughput, response-time target, implementation baseline or operational source hashes are available. [S1 D14; Q43–Q45]

### Lifecycle status and evidence

Lifecycle labels are distinct from question classifications and decision currency. UNKNOWN is the explicit evidence-gap fallback permitted by this request.

| Subject | Lifecycle status | Evidence and limits |
|---|---|---|
| Rhys-confirmed 2026-11-17 decisions | APPROVED | S1 explicitly attributes D01–D16 to Rhys, dated 2026-11-17. Approval applies only to each recorded scope. |
| Product direction attributed to Rhys in the handover | APPROVED | S3 version 1.0, 2026-11-13, §1 and stated confirmed policies. Underlying audio not supplied; attribution is documentary. |
| Proposed phased architecture, engine design and validation approach | PROPOSED | S2 §6–10; S1 carries these as the working plan. No blanket Fab/Rhys technical-design approval is evidenced. |
| Web application code/package existence and feature implementation | UNKNOWN | S1 D11 reports alpha, but no code, commit or package was supplied. Documentation does not qualify as app IMPLEMENTED evidence. |
| Installation and inactive deployment | UNKNOWN | No installation evidence supports INSTALLED-INACTIVE. |
| Application test completion | UNKNOWN | No observed runs, test counts or results support TESTED. Test lists in S1 §9 are requirements. |
| Real web quotation use | UNKNOWN | No ACTIVE evidence; S1 D11 instead records that web CALC has not been used operationally. |
| This handoff document | IMPLEMENTED | The artefact is `docs/handoff/CALC_HANDOFF.md`, created in this documentation session. This status is confined to the document, not CALC software. |

### Immediate priorities and blockers

1. Fabian obtains the actual source/code baseline and raw rate, zone and fuel samples, retaining timestamps and byte hashes.
2. Trace one complete STH estimate through customer/selling version, carrier/service, origin/location, zone, rule references, factors, charges and final amount. TransLogic evidence governs; Excel comparison is diagnostic.
3. Implement and verify imports, permissions, deterministic calculation and configured issue responses against that evidence.
4. Settle snapshot/send timing, same-customer history access, remaining retention and exceptional rollback authority with Rhys, one concrete question at a time.
5. Validate around 15 concurrent users and the existing release checks before enabling real web quoting.

Source files, source semantics and implementation/test evidence are missing. These are blockers to declaring prices verified or the web application ACTIVE, not a reason to re-ask already settled configuration choices. [S1 §13–14; S3 §13–15]

## 2. Authority and decision register

### Authority

Apply the current request's order:

1. Rhys: project owner and final decision maker.
2. Actual TransLogic exports (`rates_all.xls`, `zones.csv`, `fuel.xls`), its quotations and technical rules explicitly explained in supplied audio evidence.
3. `V2026.R2_Unlocked_STH_Freight_Calculator.xlsx`: reference for understanding logic only. A workbook difference does not itself prove a CALC error.

Those raw sources and audio files were **not supplied** here. The request names the hierarchy; it does not certify any particular source row, formula or audio quotation. Preserve source spelling such as Translogix where it appears in filenames/identifiers.

### Identifier policy

Reuse existing identifiers. The available records already use **CALC-D20261117-01–16**, Q1–Q48, and historical D001–D005. Do not renumber them into DEC identifiers or confuse them with contract D1–D8. No new decision identifier is needed for this compilation.

The request references `docs/adr/0001`–`0017`, `docs/decisions/functional_decisions.md`, `RATE-0xx`, `STH-SRC-001`, contract D1–D8 and `CA-CAL-*`. Their actual records are unavailable. No identifier is assigned a fabricated title or rule. Cross-map the existing CALC-D identifiers only after those source records are supplied.

### Current confirmed discussion decisions

All entries below: **date 2026-11-17; decision maker Rhys; lifecycle APPROVED**, as explicitly recorded in S1 §16. Currency is CURRENT except for the limited supersession stated. Reasons/consequences summarise recorded intent; they are not invented verbatim quotations.

| Existing ID | Original questions | Confirmed decision | Reason / consequence | Affected documentation | Currency |
|---|---|---|---|---|---|
| CALC-D20261117-01 | Q1/Q47 | No routine human review/correction of imports; unattended normal operation. | Reduce operator workload; repair exceptional defects at source. | APP-PLAN.md §6.3; Q1/Q47; this handoff | CURRENT |
| CALC-D20261117-02 | Q2 | Updates are automatic, not necessarily daily. | Do not impose a daily deadline; investigate actual arrival and timestamp rules. | APP-PLAN.md Q2; source contracts; this handoff | CURRENT |
| CALC-D20261117-03 | Q3 | Notify the operational team immediately on import failure; the channel remains to be agreed and is not Microsoft Teams. | Configure the approved destination/connection; documentation is not message-delivery evidence. | APP-PLAN.md §6.3; Q3; this handoff; owner clarification 2026-11-18 | CURRENT |
| CALC-D20261117-04 | Q4 | Coverage is determined by customer/carrier configuration. | No fixed discovery-stage carrier list; STH still first for validation. | APP-PLAN.md Q4; customer/carrier setup; this handoff | CURRENT |
| CALC-D20261117-05 | Q6 | Detect duplicates at import; investigate and correct the source; alert on recurrence. | Confirm keys and legitimate repetition; no arbitrary first-row choice or merge/deletion. | APP-PLAN.md §6.3; Q6; this handoff | CURRENT |
| CALC-D20261117-06 | Q19 | Customers choose cubic allowance including zero; enablement/visibility are configurable. | Separate measured from pricing volume; apply once. Free-entry mode/bounds remain unconfirmed. | APP-PLAN.md Q19; detailed product §8; this handoff | CURRENT; later D10 extends configuration |
| CALC-D20261117-07 | Q3 | Immediate alerts to the operational team for data/import errors; no separate age-only warning. The delivery channel is not yet selected. | Supersedes age-threshold questions; retain last-update display and weekly validity. | APP-PLAN.md §6.3; Q3; this handoff; owner clarification 2026-11-18 | CURRENT; clarifies D03 |
| CALC-D20261117-08 | Q6/Q38–Q41 | Postcode alone is not a universal zone key; explain conflicts and correct source. | Do not merge distinct suburbs by region/postcode. Actual matching keys need evidence. | APP-PLAN.md Q38–Q41; source contracts; this handoff | CURRENT; block-only implication SUPERSEDED BY CALC-D20261117-09 |
| CALC-D20261117-09 | Q3/Q6/Q12–Q14/Q20/Q28/Q32/Q38–Q41 | Configure warning versus blocking for applicable computable data issues. | Warning mode requires a defined calculation; no fabricated amount, unknown-as-zero or bypass of permissions. | APP-PLAN.md Q32/Q41; issue-handling settings; this handoff | CURRENT |
| CALC-D20261117-10 | Cross-cutting | Customer needs and applicable business options should be configurable. | Extends D09; does not settle technical source semantics or make security optional. | APP-PLAN.md Setup; Q19/Q32/Q41; this handoff | CURRENT |
| CALC-D20261117-11 | Q42/Q43 | Start fresh: web CALC has not been used operationally and remains alpha. | No operational estimate migration; preserve useful alpha work/evidence; distinguish Excel baseline. | APP-PLAN.md Phase 0; Q42/Q43; this handoff | CURRENT |
| CALC-D20261117-12 | Q24/Q31 | Staff always see authorised cost and choose configured margin options from a dropdown. | Customers see assigned prices only; no unrestricted ad-hoc margin entry; verify imported price meanings. | APP-PLAN.md §6.5; Q24/Q31; this handoff | CURRENT |
| CALC-D20261117-13 | Q46 | Keep quote and error logs for three months. | Not a blanket retention period for raw files, backups or all audit. Separate from visible history. | APP-PLAN.md Q46; retention design; this handoff | CURRENT |
| CALC-D20261117-14 | Q44 | Plan for approximately 15 simultaneous staff/customer users. | Planning/test target, not a verified capacity or account cap; measure other workloads. | APP-PLAN.md Phase 8; Q44/Q45; this handoff | CURRENT |
| CALC-D20261117-15 | Q4/Q31 | Site administrators activate/deactivate customers and change permissions. | Does not grant all staff data-activation or rollback permissions. | APP-PLAN.md §6.1; Q4/Q31/Q47; this handoff | CURRENT |
| CALC-D20261117-16 | Additional prompts | No mandatory scheduled margin/carrier review; no additional automation hold-back named. | Vague no-hold-back answer does not approve automatic emails, customer activation or unrelated actions. | APP-PLAN.md Current requirements; Q24; pending send controls; this handoff | CURRENT |

S1's affected-section references describe documentation to keep aligned; they are not claims that setup screens or integrations have been built.

### Earlier requirements and supersessions

| Earlier record or wording | Lifecycle / currency | Replacement and effect |
|---|---|---|
| S2 §6.3: every import requires explicit human approval and routine reconciliation | PROPOSED; SUPERSEDED BY CALC-D20261117-01 and automatic-activation direction in S3 §12 | Normal operation is unattended; validation, atomic activation, traceability and recovery remain. |
| S2 Q2 and S3 §12: daily refresh frequency | Earlier requirement; SUPERSEDED BY CALC-D20261117-02 | Automatic arrival does not prove a daily schedule. |
| Historical stale-age warning proposals/questions | PROPOSED; SUPERSEDED BY CALC-D20261117-07 | No separate age-only warning; error alerts and validity display remain. |
| Earlier fixed discovery-stage carrier/origin list question | PROPOSED; SUPERSEDED BY CALC-D20261117-04 | Coverage is configuration, not a repeated prerequisite question. |
| Block-only interpretation of a conflicting zone | PROPOSED; SUPERSEDED BY CALC-D20261117-09 | Configurable warning/blocking for defined computable prices. |
| Earlier request to decide operational estimate migration | PROPOSED; SUPERSEDED BY CALC-D20261117-11 | Start fresh; preserve alpha source/setup/evidence. |
| S3 §8 fixed cubic-allowance list as an immutable choice set | Earlier requirement; SUPERSEDED BY configurable choices in D06/D10 and S1 Q19 | Selection/visibility/available options are configurable; free-entry bounds are not confirmed. |
| S2 addendum D005: original Excel calculator works for STH | Documentary report; CURRENT as a reported baseline, not TESTED/ACTIVE evidence for web CALC | Does not conflict with unused web alpha. |
| ADR 0001 said to make Excel authoritative; replacement said to occur on 2026-11-06 | UNKNOWN: both historical records were cited by the requester but not supplied | Follow the current explicit TransLogic hierarchy. Do not mark an unseen ADR as APPROVED or assert the historical event independently verified. Obtain ADR/replacement evidence and preserve both records when available. |

### Contradictions resolved or left explicit

- **Document versus runtime evidence:** design text and AI statements do not establish implementation, tests or production use. S1 Q43 and D11 control the current reported baseline.
- **Snapshot timing:** S2 §6.5 lists saving at the end of a request; S3 §11 explicitly leaves the trigger undecided. S1 Q31/§14 retains the gap. Immutable snapshots are required, but automatic save/email triggers are not approved.
- **Retention:** three months applies to quote/error logs (D13). It does not silently replace 14-day visible history or define all raw-file/version/backup retention.
- **Numbering:** spoken Q43 margin discussion belongs to Q24/Q31; spoken Q44 retention to Q46; concurrency to Q44; customer administration to Q4/Q31. Scheduled review and automation exclusions were additional prompts, not answers to original Q47/Q48. S1 §16 records the correction.
- **Completeness:** “all 48 answered” was an earlier overstatement corrected in S1 §16. All are recorded; technical and business gaps remain.
- **Single-file state versus historical appendices:** S1 contains old unanswered wording inside its decision history. Current Q1–Q48 and later explicit D01–D16 govern; history does not reopen them.
- **Source rate changes:** this request says `rates_all.xls` changes daily; D02 says automatic feed arrival need not be daily. Treat these as separate facts about source mutation and delivery. No current file version is certified.
- **Language:** Australian English is required here; `docs/22_language_policy.md` was not supplied, so compliance with its unseen detailed rules is UNKNOWN. No Spanish document content is reproduced.

## 3. Technical information and operational source register

### Documented design, not observed implementation

S1 §6 describes identity/authorisation, master data, import/staging/versioning, a typed rating engine, estimate service, audit/observability and a web interface. This is **PROPOSED** architecture unless a specific business requirement has Rhys's approval. Backend language/framework, database engine, hosting, Docker services, repository layout and deployed endpoints are **UNKNOWN**. The requirement for background/chunked imports does not identify a queue technology.

Documented relationships: user → permitted customers → allowed carrier/selling versions → services, origins/destinations, zones, rates, cubic factors, limits and surcharges. Source identifiers must preserve text/leading zeros. Imported expressions must not be executed as arbitrary code. Actual keys and field meanings, including `master_rate`, `rate_no`, `run_rate`, `break`, `item_no`, `filter_field`, `unit`, `rate`, `basic_charge` and `min_charge`, remain investigation tasks. [S1 §6, Q8–Q15, Q18–Q27; S3 §13]

### Product and calculation requirements to preserve

| Area | Requirement / evidence | Lifecycle |
|---|---|---|
| Shipment entry | Product-list, custom-entry or mixed mode by customer; per-item weight/dimensions multiplied by quantity. Custom cartons/pallets need no SKU. [S3 §4–5; S1 Q36] | APPROVED direction attributed to Rhys in S3, 2026-11-13 |
| Default origin and coverage | Woodville North SA 5012 default depot; alternative pickups/rates through setup. Actual enabled coverage is configuration. [S3 §4; D04] | APPROVED |
| Pallets | Full measured loaded L×W×H; no additional component cubic volume. Contents plus configurable tare unless already included. Approximately 32 kg is a suggested starting tare, not a universal verified weight. [S3 §6] | APPROVED workflow; exact tare values PROPOSED |
| Kits | Expand parent into multiplied child lines; count children only; allow calculation-only quantity changes; reject missing/recursive definitions. [S3 §7] | APPROVED direction |
| Product/Stock discrepancies | Greater weight and greater complete source volume; do not combine maximum dimensions into an invented box. Preserve sources; warning/admin notification when used. Overlength source handling remains open. [S3 §5; Q34] | APPROVED policy; detailed checks UNKNOWN |
| Cubic allowance | Customer selection, including zero, configurable visibility/choices; affects pricing volume only, once. [D06/D10; Q19] | APPROVED; exact engine placement UNKNOWN |
| Price | Greater actual/cubic chargeable weight baseline; basic/variable charge and minimum; configured fixed/percentage fees, fuel, security, overlength and extras. Exact factors/order/bases/rounding must come from real source evidence. [S3 §9,13] | APPROVED capability; exact mappings UNKNOWN |
| Staff/customer pricing | Authorised cost and configured margin dropdown for staff; assigned selling prices only for customers. No double margin. [D12; S3 §3] | APPROVED |
| Tax and validity | Ex GST default, optional calculator-wide inclusive display; Monday–Sunday validity, expired-rate warning, immutable history/current-rate Create as new. [S3 §9–11] | APPROVED |
| Emails/history | Customer/Steadfast recipient choices and configured automatic copy; reference, shipment, selected service, price, dates, warnings and estimate qualification. Exact send/save timing and same-customer visibility remain open. [S3 §11] | APPROVED capability; unresolved triggers PROPOSED |
| Notifications | Immediately notify the operational team of import/data errors through an agreed channel. Microsoft Teams is not used. The measurement override/discrepancy admin email requirement is separate. [D03/D07; S3 §5; owner clarification 2026-11-18] | APPROVED requirement; channel and integration implementation UNKNOWN |

### Active operational sources

“Candidate” below describes a source's intended role, not a lifecycle status. No source is labelled ACTIVE without a verified received version and observed quotation-use evidence.

| Source named in the request | Intended authority | Generation date / SHA-256 / activation | Evidence limit |
|---|---|---|---|
| `rates_all.xls` | Actual TransLogic rate source; requester says it changes daily | UNKNOWN / UNKNOWN / UNKNOWN | File not supplied. No row or rate traversal verified. |
| `zones.csv` | Actual TransLogic zone source | UNKNOWN / UNKNOWN / UNKNOWN | File not supplied; S3 §12 reports carrier codes exist. |
| `fuel.xls` | Actual TransLogic fuel source | UNKNOWN / UNKNOWN / UNKNOWN | File not supplied; surcharge bases/mapping unverified. |
| `V2026.R2_Unlocked_STH_Freight_Calculator.xlsx` | Historical logic/reference workbook | UNKNOWN / UNKNOWN / UNKNOWN | File not supplied. Do not use as silent fallback or sole correctness oracle. |
| Product/Stock/customer/location and carrier/service inputs | Official operational exports and configured manual records where agreed | UNKNOWN / UNKNOWN / UNKNOWN | Exact filenames/contracts/versions not provided. |

For each future received source, record filename, receipt date/time with Adelaide offset, source generation time, exact byte SHA-256, schema, validation outcome and active version identity. Hash each new version of `rates_all.xls`; do not reuse a hash after contents change. This is a required evidence-capture procedure, not a completed import.

### FTP, startup, installation, testing and rollback

| Procedure | What the supplied files support | What must be obtained |
|---|---|---|
| FTP integration | Source discussions refer to operational exports/imports; no verified connection details or working FTP procedure were supplied. | Approved source contracts, delivery mechanism, completion/atomic-file convention, schedule/polling, retries and diagnostics. Do not include credentials. |
| Startup | UNKNOWN; no runtime or dependency manifest inspected. | Source-backed runbook and environment requirements. Do not invent shell commands. |
| Tests | S1 §9 requires data-format/duplicates/references/range tests; rating boundaries/units/surcharges/margins; negative access tests; UI/failed-import and rollback checks. D14 adds roughly 15 concurrent users. | Executable tests, exact runs/counts/results, source hashes and comparison traces; none observed here. |
| Package installation / INSTALLED-INACTIVE | UNKNOWN; no package or installer supplied. | Exact package identity/hash, supported environment, install steps, inactive-state verification and authorisation. |
| Activation | Validated consistent updates; no routine manual approval. [S1 §6.3; D01] | Verified adapter behaviour, active-version records and exceptional activation permissions. |
| Reversal/recovery | Preserve versions, return to compatible last stable data and verify after rollback; incident procedure required. [S1 §2, §6.3, §10; Q48] | Exact commands/package rollback, permitted operator, compatibility checks, wrong-price notification and issued-estimate handling. |

The only confirmed documentation path created by this session is `docs/handoff/CALC_HANDOFF.md`. Other paths named by the request are references, not an inspected repository structure.

## 4. Original Q1–Q48 register

Classifications use only **answered**, **partly answered**, **superseded**, **technical investigation**, **deferred**, or **needs Rhys's decision**. They are not software lifecycle labels. A multi-part question stays partly answered where detail remains. Original question text and fuller evidence are in S1 §13; descriptions below are summaries to avoid copying the plan. D identifiers mean the existing CALC-D20261117 identifiers; H/P in S1 mean handover/original plan.

| ID / original subject | Classification | Current answer | Owner and practical consequence / remaining work |
|---|---|---|---|
| Q1 — Data authority and reviewers | partly answered | Complete official exports are authoritative. CALC runs unattended with no routine manual reviewer or correction task. Rhys makes final business decisions; Fabian investigates source/code semantics. Repair exceptional defects at source. [S1 §13 Q1] | Fabian: technical detail; Rhys: business/permission decision. Operating model settled; exact source contracts and emergency permissions remain technical work. |
| Q2 — Update frequency and currency | technical investigation | Updates are automatic, not necessarily daily. Source generation timestamps establish currency after validation. [S1 §13 Q2] | Fabian: inspect source evidence. Technical investigation. Identify schedule/arrival mechanism, timestamps, ties and missing-timestamp handling. |
| Q3 — Failed, invalid or expired sources | partly answered | Alert the operational team immediately for import/data errors through a channel still to be agreed; Microsoft Teams is not used. No separate alert or warning based solely on update age. Keep last valid data after failed imports, display last successful update and weekly validity; expired rates warn. Configurable warn-or-block behaviour applies to computable affected results. [S1 §13 Q3; owner clarification 2026-11-18] | Fabian first; Rhys for residual policy. Specify Monday source-period attribution, the approved notification connection and technical quarantine boundaries. No assumed daily deadline or grace-period question remains. |
| Q4 — Datasets and enabled coverage | partly answered | All operational datasets are complete. STH is first for testing/enablement. Coverage is defined by customer/carrier configuration; no fixed discovery-stage list is required. Site administrators activate/deactivate customers and manage their permissions. [S1 §13 Q4] | Fabian: technical detail; Rhys: business/permission decision. Validate configured paths and readiness using §10; do not reopen the fixed-list question. |
| Q5 — Negative, extreme or unusual values | technical investigation | No universal meaning is established; do not silently discard anomalies or turn unknown values into zero. [S1 §13 Q5] | Fabian: inspect source evidence. Investigate. Fabian profiles real records and identifies valid exceptions versus errors. Rhys decides only unresolved business meanings. |
| Q6 — Duplicates and source correction | partly answered | Detect duplicates during import; investigate the initial occurrence and correct at source. Recurrences immediately alert the operational team through the agreed channel. Distinguish legitimate repeated rows from conflicts; no arbitrary first-row selection or automatic merge/deletion. [S1 §13 Q6; owner clarification 2026-11-18] | Fabian: technical detail; Rhys: business/permission decision. Fabian confirms identifiers, sequence scope and validation/quarantine boundaries; applicable computable issues use configured warn/block response. |
| Q7 — Product and Stock categories | technical investigation | Products supply the master/description; Stock represents warehouse quantities. Their category fields are not proven equivalent. [S1 §13 Q7] | Fabian: inspect source evidence. Investigate. Determine whether either category affects selection or pricing; do not impose unnecessary category mapping if irrelevant to CALC. |
| Q8 — Entry Rate Card and references | technical investigation | Customer/carrier/selling-version relationships are required, but actual entry fields and reference links are unverified. [S1 §13 Q8] | Fabian: inspect source evidence. Investigate. Trace master_rate, rate_no and run_rate through a real STH example. |
| Q9 — Rate-field meanings | technical investigation | Meanings of break, item_no, wildcards, references, types and customer-price fields remain unverified. [S1 §13 Q9] | Fabian: inspect source evidence. Investigate. Document actual semantics, units and supported rule representations; never execute arbitrary imported expressions. |
| Q10 — Sequence ties and file order | technical investigation | No confirmed tie-breaking or blank-sequence rule exists. [S1 §13 Q10] | Fabian: inspect source evidence. Investigate. Establish whether source order matters; do not invent a first-row-wins rule. |
| Q11 — Several matching rate rules | technical investigation | No universal first-match, priority or accumulation policy is confirmed. [S1 §13 Q11] | Fabian: inspect source evidence. Investigate. Establish deterministic behaviour for actual rate structures. |
| Q12 — Missing/cancelled/expired references | partly answered | Missing essential paths cannot produce a valid price; independent valid options continue. Expired rates may quote with warnings; successfully removed records cannot. [S1 §13 Q12] | Fabian: technical detail; Rhys: business/permission decision. Partial. Classify cancelled/uninterpretable references and distinguish expiry from removal. Apply D09 configurable issue response where a defined price is computable; this does not resolve source semantics or permit fabricated prices. |
| Q13 — Essential versus optional references | technical investigation | Unknown required charges must not silently become zero. [S1 §13 Q13] | Fabian: inspect source evidence. Investigate. Fabian identifies which references are essential or demonstrably inapplicable in each path. Apply D09 configurable issue response where a defined price is computable; this does not resolve source semantics or permit fabricated prices. |
| Q14 — Rate Card cycles | technical investigation | The plan requires cycle detection; arbitrary recursive traversal is unsafe. [S1 §13 Q14] | Fabian: inspect source evidence. Investigate. Whether any source cycle has legitimate semantics remains unconfirmed. Do not silently ignore one or treat it as a valid price. Apply D09 configurable issue response where a defined price is computable; this does not resolve source semantics or permit fabricated prices. |
| Q15 — Cubic factors and rounding | partly answered | Use carrier-specific cubic conversion and the greater of actual/cubic chargeable weight as the baseline. Units are kg, metres and m³. [S1 §13 Q15] | Fabian: technical detail; Rhys: business/permission decision. Partial. Verify each factor's source, units, rounding and rate-specific exceptions. |
| Q16 — Volume of grouped freight | answered | A measured full pallet uses overall loaded L × W × H, including gaps/overhang. Do not also add contents' volumes. [S1 §13 Q16] | Fabian: implement/verify scope. Settled for initial scope. Advanced packing optimisation is outside scope; other future grouping modes need explicit rules. |
| Q17 — Pallet tare and volume | answered | Configurable pallet types/tare. Add tare unless entered weight includes it; full loaded dimensions determine volume. Around 32 kg was a configurable starting suggestion. [S1 §13 Q17] | Fabian: implement/verify scope. Settled. Configure actual pallet values; 32 kg is not a universal verified weight. |
| Q18 — pal, pal1, pal2, pallet and lift | technical investigation | Their imported meanings and units are not established by the pallet UI requirements. [S1 §13 Q18] | Fabian: inspect source evidence. Investigate. Inspect fields and source calculations; do not infer meaning from field names. |
| Q19 — Cubic allowance | partly answered | Customers may select cubic allowance including zero; enablement, visibility and available options are configurable. Preserve measured volume; change pricing volume only, separately from selling margin. Earlier 0%,1%,2%,5%,10%,15% choices are reference values, not an immutable list. [S1 §13 Q19] | Fabian first; Rhys for residual policy. Verify engine placement and pallet handling to apply once. Settings must express available choices; free numeric entry and its bounds have not been explicitly agreed. Do not repeat the already answered configurability question. |
| Q20 — Operational confirmation limits | partly answered | Eligibility limits are configurable. Measurement conflicts warn; known service unavailability shows a reason. [S1 §13 Q20] | Fabian: technical detail; Rhys: business/permission decision. Partial. Obtain actual carrier/service thresholds and confirmation rules; conversational weight examples are not specifications. Apply D09 configurable issue response where a defined price is computable; this does not resolve source semantics or permit fabricated prices. |
| Q21 — Charge calculation order | partly answered | Baseline supports basic plus variable charge, a minimum and actual/cubic chargeable weight, plus configured fuel and extras. [S1 §13 Q21] | Fabian first; Rhys for residual policy. Partial. Trace the precise order and exceptions for each real rate path. The baseline is not a complete universal formula. |
| Q22 — Percentage surcharge base | technical investigation | Support fixed and percentage fees, recognising decimal percentage conventions. [S1 §13 Q22] | Fabian: inspect source evidence. Investigate. Establish each fee's included/excluded components and subtotal. Do not assume all percentages use the same total. |
| Q23 — Cost versus selling price | partly answered | Separate cost and selling versions; never apply margin twice. [S1 §13 Q23] | Fabian first; Rhys for residual policy. Partial. Identify what each imported field/version actually represents. |
| Q24 — Margin rules and authority | partly answered | Staff always see authorised carrier cost and select/apply a configured margin from a dropdown. Customer pricing remains assigned through setup. Do not double-apply margin to imported selling rates. [S1 §13 Q24] | Fabian: technical detail; Rhys: business/permission decision. Verify cost/selling mappings, per-service exceptions, master-edit permissions and effective timing. No unrestricted ad-hoc percentage typing was approved; no scheduled margin/carrier review is required. |
| Q25 — Rounding | technical investigation | No precise rounding policy is established. [S1 §13 Q25] | Fabian: inspect source evidence. Investigate. Verify precision, rounding mode and stage for weights, charges, subtotals and totals against real results. |
| Q26 — GST | answered | Default Ex GST; an optional calculator-wide setting additionally shows GST and the inclusive total. [S1 §13 Q26] | Fabian: implement/verify scope. Settled. Per-user/customer tax preferences are unnecessary initially. |
| Q27 — Accumulating/exclusive charges | technical investigation | Both behaviours may be needed; exact combinations are unverified. [S1 §13 Q27] | Fabian: inspect source evidence. Investigate. Identify compatible, exclusive and dependent fees from actual rate structures. |
| Q28 — Service eligibility | partly answered | Respect customer, carrier, service, origin/destination permissions and configured service limits; include selected applicable extras. [S1 §13 Q28] | Fabian: technical detail; Rhys: business/permission decision. Partial. Establish actual limits and supported combinations for initial services. A rate's existence alone does not prove eligibility. Apply D09 configurable issue response where a defined price is computable; this does not resolve source semantics or permit fabricated prices. |
| Q29 — Estimate versus binding quote | deferred | CALC produces qualified freight estimates. Saving preserves the result; it does not create a price guarantee. Disclaimer wording is not legally certified. [S1 §13 Q29] | Fabian: implement/verify scope. Scope-limited. A binding-quotation workflow is unnecessary for the agreed initial calculator. Any future guarantee/legal approval policy remains separate and unapproved. |
| Q30 — Validity and later rate changes | answered | Calculator-wide Monday–Sunday validity. Preserve original history/dates; viewing does not recalculate. Create as new uses current rates; expired prices warn. [S1 §13 Q30] | Fabian: implement/verify scope. Settled. Stale-source attribution stays under Q3. Per-rate-card validity is deferred. |
| Q31 — Price, trace and history visibility | partly answered | Staff see authorised cost and configured margin choices. Customers receive only assigned selling prices. Site administrators control customer activation and permissions; enforce access and confidentiality in backend, UI, breakdowns and emails. [S1 §13 Q31] | Fabian: technical detail; Rhys: business/permission decision. Same-customer history sharing and detailed audit/trace/commercial-master/rollback permissions remain to be specified. |
| Q32 — Blocking versus warnings | partly answered | Applicable data issues have configurable warn-or-block handling. Warning mode may show a computable price with a clear accuracy/issue message. Stock shortage does not block; expiry warns; valid independent options continue. Errors immediately notify the operational team through the agreed channel and are repaired at source. [S1 §13 Q32; owner clarification 2026-11-18] | Fabian: technical detail; Rhys: business/permission decision. Fabian defines issue categories and deterministic calculations. Settings cannot fabricate prices, turn unknown required charges into zero or bypass permissions/confidentiality. |
| Q33 — Stock availability | answered | Informational only. Show Not in stock without blocking selection/calculation. No reservation or inventory management. [S1 §13 Q33] | Fabian: implement/verify scope. Settled. No need to ask again. |
| Q34 — Product/Stock conflicts | partly answered | Use greater weight and greater complete source volume; warn/notify when used. Do not combine maximum dimensions into an invented box; preserve source data. [S1 §13 Q34] | Fabian first; Rhys for residual policy. Partial. Product master supplies description generally; explicit conflict precedence, category treatment and overlength dimensions still need confirmation. |
| Q35 — Blank/repeated serial numbers | technical investigation | No definition or uniqueness rule is established. [S1 §13 Q35] | Fabian: inspect source evidence. Investigate, with scope check. Needed for safe stock identity/imports if those rows are used; serial selection/tracking is not a new calculator feature requirement. |
| Q36 — Custom freight | answered | Customer setup enables products, custom freight or both. Custom cartons/pallets need no SKU; quantity, per-item weight/dimensions and authorised route inputs are required. [S1 §13 Q36] | Fabian: implement/verify scope. Settled. Existing product-dimension editing is a separate permission; pallet tare handling still applies. |
| Q37 — Kits | answered | Expand parent into child lines, multiply quantities by kit count and count children only. Allow calculation-only quantity adjustments; preserve definitions. [S1 §13 Q37] | Fabian: implement/verify scope. Settled. Prevent missing components and recursion; pallet grouping follows actual loaded measurements. |
| Q38 — Zones versus location authority | technical investigation | Respect full location and carrier/service context; postcode alone is not a universal zone identity. Explain genuine conflicts clearly, alert immediately and correct at source. [S1 §13 Q38] | Fabian: inspect source evidence. Determine authoritative conflicting fields from actual exports. Applicable computable issues use configured warn/block handling. |
| Q39 — Aliases and unusual locations | partly answered | Search suburb/state/postcode and preserve text codes. Distinct suburbs such as Woodville and Woodville North must not be conflated merely because they share a region or postcode. [S1 §13 Q39] | Fabian first; Rhys for residual policy. Verify aliases, short-postcode handling and geographic scope from source evidence; spoken examples do not certify actual zone assignments. |
| Q40 — Zone dependencies | technical investigation | Use exported carrier codes to derive links automatically where sufficient. Zone identity may require suburb/locality and other attributes, not just postcode. [S1 §13 Q40] | Fabian: inspect source evidence. Fabian establishes actual origin/service/load-type dependencies and complete matching keys. |
| Q41 — Competing zone matches | partly answered | For a genuine zone conflict, settings allow a computable price with a clear issue/accuracy warning or blocking the affected result. Continue independent valid options; notify the operational team immediately through the agreed channel and repair at source. [S1 §13 Q41; owner clarification 2026-11-18] | Fabian first; Rhys for residual policy. Determine a supported deterministic selection policy before pricing a disputed path. No arbitrary first-row choice or invented price is authorised. Warn/block default and configuration scope remain design details. |
| Q42 — Historical migration | answered | Start fresh. The web application has not been used operationally and there are no historical operational estimates to migrate. [S1 §13 Q42] | Fabian: technical detail; Rhys: business/permission decision. Migration of old operational estimates is not required. Preserve useful alpha code, setup, tests and evidence; this is not permission to delete them. |
| Q43 — Previous deployed version | technical investigation | The web CALC is unused alpha. This is distinct from the original Excel calculator reported working for STH. Preserve useful existing work/layout. [S1 §13 Q43] | Fabian: inspect source evidence. Fabian identifies the actual repository, database, snapshots and deployment baseline. No hosting/backup technology was established by the unclear spoken cloud reference. |
| Q44 — Future capacity | partly answered | Approximately 15 simultaneous staff/customer users. [S1 §13 Q44] | Fabian first; Rhys for residual policy. Concurrency target answered. Fabian tests this target; source volumes/traffic growth and performance remain planning work. |
| Q45 — Performance | needs Rhys's decision | Plan requires volume/timing tests and background processing, but specifies no numeric response/import target. [S1 §13 Q45] | Fabian: technical detail; Rhys: business/permission decision. Still relevant. Fabian benchmarks and proposes targets for Rhys to confirm; do not invent an SLA. |
| Q46 — Retention | partly answered | Quote and error logs: three months. Visible history remains separately configurable, initially about 14 days. [S1 §13 Q46] | Fabian: technical detail; Rhys: business/permission decision. Partial. Define raw-file/version/other-audit/backup retention and align saved estimates with log purging before deletion. |
| Q47 — Activation and duties | partly answered | Validated automatic updates activate without routine human approval or manual correction. Site administrators control customer activation; that is separate from data activation. No mandatory scheduled commercial review is required. [S1 §13 Q47] | Fabian: technical detail; Rhys: business/permission decision. Exceptional data activation/rollback permissions and separation of duties remain open. The spoken scheduled-review answer was not an answer to original Q47. |
| Q48 — Wrong active prices | partly answered | Plan already requires reversible activation, return to last stable data, post-activation checks, tested rollback and an incident procedure. [S1 §13 Q48] | Fabian: technical detail; Rhys: business/permission decision. Partial, not unanswered. Specify who may pause affected quoting/roll back, compatible-version recovery, verification, notifications and treatment of issued estimates. No new emergency authority is granted here. |

For Q29, “deferred” applies to any future binding-quotation feature; the current estimate-only scope is answered. For Q42, no operational estimate migration is required; this answer does not authorise deleting alpha setup/evidence. Q1/Q4/Q6/Q19/Q24/Q44/Q47 contain settled operating/configuration answers alongside technical or permission gaps. No question is wholly marked superseded where only one subpart changed.

### Additional questions without duplicating the register

No new decision IDs are assigned to unanswered questions.

| Additional topic / source | Mapping or classification | Owner and consequence |
|---|---|---|
| Durable snapshot creation, Save without emailing, exact email trigger and duplicate-send prevention [S3 §11; S1 §14] | needs Rhys's decision; related Q30/Q31/Q46 but trigger not explicitly asked in original wording | Rhys decides when an estimate is final; Fabian designs idempotent sending/snapshot behaviour. Do not email on every field edit. |
| Same-customer users sharing history [S3 §11] | partly answered under Q31; no duplicate question | Rhys sets access policy; Fabian enforces backend query/detail access. |
| Weekly attribution of an older source across Monday [S3 §10] | partly answered under Q3/Q30 | Fabian proposes source-period determination; Rhys settles any remaining business meaning. Do not relabel old data current. |
| Cubic allowance free-entry versus configurable choices [S1 Q19] | partly answered under Q19 | Configurability is settled. Exact input mode/validation is not; do not re-ask customer-selection permission. |
| Workbook versus app comparison | technical investigation under Q21/Q25/Q43 | Use matched source versions and actual TransLogic quotation traces; workbook difference alone is not a defect. No comparison file was supplied. |
| Daily handoff, contract D1–D8, RATE-0xx, STH-SRC-001 and CA-CAL-* follow-ups | UNKNOWN evidence; technical investigation to inventory supplied records when available | Fabian supplies actual documents/identifiers. Contents/questions cannot be reconstructed from names. Avoid claiming these are answered or assigning new IDs that collide. |
| 2026-11-13 product direction | Mapped into Q1–Q48 and technical/product requirements above | Source S3 was received. No second unseen Rhys document is assumed. |
| More detailed language policy | technical investigation | Obtain `docs/22_language_policy.md`; Australian English requirement is clear, unseen file contents are not. |

## 5. Risks and safeguards

| Risk | Evidence / current control | Lifecycle / remaining consequence |
|---|---|---|
| Wrong source authority | Current request prioritises TransLogic over workbook; S2 §2 rejects workbook as a silent database fallback. | PROPOSED implementation until verified; obtain ADR supersession records. |
| Mixed or obsolete data disguised as current | S1 §6.3 requires consistent versions and failure recovery; no age-only alert does not mean fresh data. | APPROVED operating requirements D01/D02/D07; implementation UNKNOWN. |
| Ambiguity produces arbitrary price | Q6/Q10–Q14/Q41; D05/D09 forbid arbitrary selection/fabrication. | APPROVED configurable response; exact source semantics UNKNOWN. |
| Double margin, pallet tare, parent/child or allowance counting | S3 §5–9; D12. | APPROVED requirements; tests UNKNOWN. |
| Cross-customer price/data exposure | S3 §3; D12/D15; S1 negative authorisation test plan. | APPROVED restriction; enforcement/test evidence UNKNOWN. |
| Over-broad deletion from three-month retention | D13 expressly limits quote/error logs; Q46 unresolved record types. | APPROVED limited retention, broader purge PROPOSED. Do not delete unknown categories. |
| Documentation claims treated as completed tests/active use | S1 D11/Q43 and this request's lifecycle scheme. | No software IMPLEMENTED/TESTED/ACTIVE claim without commit/package/run evidence. |
| Knowledge lost or stale handoff | Preserve decisions and append dated source-backed history; use source hashes and current-version identity. | This artefact IMPLEMENTED; ongoing maintenance is an instruction, not a scheduled automation. |

## 6. Handover to the next AI

### Reading and work order

1. Read this current-state section, authority and lifecycle rules.
2. Read S1 current requirements, §13 Q1–Q48, §14 priorities and D01–D16. Treat S1 historical appendices as dated evidence.
3. Read S3 §5–13 for physical input/calculation rules and remaining source questions; apply the later D decisions.
4. Read S2/S4 only to understand earlier reasoning and superseded questions.
5. Obtain missing ADRs/contracts, raw sources and test/runbook evidence before claiming implementation or source correctness. Reuse their real IDs when received.
6. Have Fabian resolve source/code questions first. Ask Rhys one concrete remaining business question at a time; record the answer, attribution, date and impact before moving on.
7. Begin implementation/verification from the documented source contracts and priorities; preserve layout and scope, validate STH iteratively, then broaden customer enablement.

### Do not do

- Do not mark all 48 fully answered; invent data/field meanings; infer daily feed arrival; add an age-only warning; demand a fixed initial carrier list; or assign routine manual reconciliation.
- Do not claim an unseen ADR, contract, code file, Docker configuration, commit, installer or test was inspected.
- Do not label the web application ACTIVE because Excel is reported working for STH.
- Do not treat “no additional automation hold-back” as unrestricted permission to send messages, activate customers, deploy or email estimates.
- Do not fabricate a price in warning mode, use first-row-wins without evidence or make confidentiality optional.
- Do not print secrets, personal email addresses or personal audio conversations.

### Maintenance at session or milestone close

Update the short current state and relevant question/decision records. Add one dated history entry for a day with activity; within that day append distinct session/milestone subentries so prior work is preserved. Put newest day first. Retain original decision IDs, approval evidence, replaced decisions and failed attempts relevant to continuity.

Use Adelaide dates and include an offset if exact event times are evidenced; do not invent times. Capture file/version/hash and exact package/commit/test results only when available. No daily files are copied wholesale. If a prior handoff later becomes available, reconcile and preserve it rather than overwriting its history.

## 7. Unavailable references and verification limits

No existing CALC_HANDOFF.md was present at the requested local path or found by two scoped filename searches. This supports creating the initial available record; it does not prove that no copy exists elsewhere.

| Cited document / artefact not received as a standalone source here | Consequence |
|---|---|
| `APP CONTEXT.md` | No independent contents or updated decisions can be asserted. |
| `CALC.APP.frontend.md`, `CALC.APP.backend.md` | Only mentions in received documents; no framework/interface/backend implementation claims. |
| `docs/22_language_policy.md` | Detailed policy not verified; use Australian English as requested. |
| `docs/adr/0001`–`0017` and 2026-11-06 TransLogic precedence decision record | Exact titles, acceptance, authorship, chronology and supersession links UNKNOWN. |
| `docs/decisions/functional_decisions.md` | Functional decision catalogue and IDs unavailable. |
| `RATE-0xx`, `STH-SRC-001`, contract D1–D8 and `CA-CAL-*` source records | Cannot map, quote or resolve their rules/questions from identifiers alone. |
| `docs/handoff/daily/` records, reports and contracts not otherwise named/provided | Daily implementation/test history cannot be independently reconstructed. |
| `docs/fuentes/audios/` technical transcripts | No audio quotation or personal transcript content used; technical audio evidence not directly inspected. |
| `CALC.DocumentationReview.v2026.11.11.1.md` | S2 summarises its existence; R01–R15 details not independently read. |
| Historical workbook/FTP analyses referenced by S2/S3, including `CALC.ANALISIS_ESTRUCTURAL_ARCHIVOS_FTP.md` | Profiling statements remain reported historical context; raw findings not independently verified here. |
| `rates_all.xls`, `zones.csv`, `fuel.xls`, `V2026.R2_Unlocked_STH_Freight_Calculator.xlsx` | No operational dates/hashes, real quotations or calculation comparisons can be certified. |
| App code/packages, Git metadata, Docker configuration, install/test/rollback runbooks and workbook/app comparison reports | No software implementation, installation, exact procedure, observed test or real-use evidence. |

APP PLAN.md **was** received (S2); the updated APP-PLAN.md is S1. The original 13 November analysis names a “(1)” handover copy; this session actually read the supplied “(2)” copy. No byte identity between unseen copies is asserted. The longer consolidated project document was not needed as an additional source for this record; its contents/appendices are not claimed independently reviewed here.

## 8. Daily history — newest first

### 2026-11-17 — Current documentation session, with earlier activity reconstructed

**Date / objective:** 2026-11-17, Australia/Adelaide. Create the requested master continuity record using only supplied project documents. Earlier work on this date is **RETROSPECTIVE**, supported by S1 D01–D16 and §17. Exact discussion/session times are UNKNOWN.

**Work done, files, commits or packages:**
- Current session: read S1 in two complete version-10 windows plus supplied S2/S3/S4, recorded evidence limits and documentation hashes, reconciled the 48-question register and created `docs/handoff/CALC_HANDOFF.md`.
- Earlier documented milestone: integrated requirements and Q1–Q48 into APP-PLAN.md; S1 §17 records the update. This is documentation work; no commit or application package was supplied.
- Prior file search found no available handoff to preserve. No code/Git/Docker inspection occurred.

**Questions and confirmed answers:** S1 attributes D01–D16 to Rhys on this date: unattended imports; automatic not necessarily daily arrival; immediate alerts to the operational team through a channel still to be agreed (not Microsoft Teams, per owner clarification 2026-11-18); no age-only warning; configured coverage; source duplicate correction; configurable cubic allowance and issue handling; unused alpha/fresh start; staff cost/configured margin dropdown; three-month quote/error logs; around 15 concurrent users; site-admin customer permissions; no mandatory review schedule/additional hold-back.

**Decisions and events:** preserved existing CALC-D IDs; corrected original/spoken question mapping; applied later explicit answers over historical proposals. Current request establishes TransLogic-over-workbook precedence and strict evidence labels for this document. No date/author/content is invented for missing ADRs.

**Tests — what ran, result, limitations:** documentation checks only: 48 unique original Q identifiers in order, required sections, evidence/currency fields, source hashes, and scan for secrets/personal addresses. Results: 48 unique question rows in original order; 16 unique existing CALC-D decision rows; eight required sections present; four documentation SHA-256 values matched available bytes; zero personal email addresses or credential assignments found. These are document consistency checks, not application test runs. These checks do not establish TESTED for CALC. No application test ran or test count was available.

**Problems, fixes and open items:** original plan contains stale wording inside historical records; labelled and reconciled in this handoff. Missing source/ADR/contract files prevent verification. Save/send timing, shared-customer history, full retention, exact pricing semantics and emergency authority remain open.

**State at close / next steps:** documentation artefact IMPLEMENTED when saved. Rhys's recorded decisions APPROVED within their scope. Application implementation/install/test/activation UNKNOWN. Fabian obtains source/implementation evidence, then follows §6 priorities. No notification was sent or live data changed.

### 2026-11-13 — RETROSPECTIVE: consolidated product direction and question comparison

**Date / objective:** 2026-11-13, Australia/Adelaide; from S3 document date and S4 analysis date, not an observed work session.

**Work done / files:** S3 describes Rhys's direction for Fabian; S4 compares handover answers against all 48 plan questions. No commit/package evidence.

**Questions / confirmed answers:** S3 records ownership, STH-first use, product/custom modes, physical measurements, pallets, kits, cubic allowance, GST, estimates, history and automatic import direction. S4 assesses coverage as 7 answered, 21 partial, 16 technical and 4 open. Those counts are historical and superseded by later answers/classifications, not a current completion metric.

**Decisions / events:** S3 says later explicit direction supersedes earlier conflicting proposals and describes itself as a planning/implementation handover, not proof of runtime behaviour.

**Tests:** UNKNOWN; no observed application test or source-row validation in S3/S4.

**Problems / fixes / open items:** missing raw exports and code; rate traversal, rounding, source meanings and some business timing remained open. Superseding 2026-11-17 answers are now incorporated above.

**State at close / next steps:** planning direction attributed to Rhys; implementation/verification UNKNOWN. Next documented task was source investigation and question reconciliation.

### 2026-11-11 — RETROSPECTIVE: documentation review addendum

**Date / objective:** 2026-11-11, Australia/Adelaide; from S2's dated addendum.

**Work done / files:** S2 reports that six Markdown documents were compared and records an external review file plus clarification register R01–R15. Only S2's addendum is directly available here; the six-source review is reported, not independently repeated.

**Questions / confirmed answers:** historical D001–D005 cover review-first/documentation instructions, following the plan, participant authority clarification, traceable answers and the reported working Excel STH baseline. Do not confuse these with missing contract D1–D8.

**Decisions / events:** functional assumptions and missing authority/source mappings were flagged for clarification. No new commercial rates or runtime behaviour were certified by the review.

**Tests:** UNKNOWN; the addendum explicitly says workbook, raw exports, code, database and deployed runtime were not inspected.

**Problems / fixes / open items:** competing documentation references, activation policy, permission scope, mappings and operational targets needed follow-up. Later D01–D16 supersede only the relevant portions.

**State at close / next steps:** documentation/discovery stage, with source inventory and governance work next. No source evidence supports dates earlier than this for a daily activity entry; the requested 2026-11-06 precedence event remains an unverified historical reference, not an invented daily log.

### Reusable entry template

- Date / Objective
- Work done, with exact files, commits or packages where evidenced
- Questions asked and confirmed answers, including respondent
- Decisions and events, retaining existing IDs and supersession
- Tests: exact scope, count, result and limitations
- Problems, fixes and open items
- State at close and next steps
- If RETROSPECTIVE: source files/sections and unconfirmed parts

Do not create entries for days without evidenced activity.

