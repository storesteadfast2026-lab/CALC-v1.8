# Work Plan for Rebuilding the Freight Estimating Application

## 1. Purpose of this document

This plan proposes rebuilding the freight estimating application from the ground up, using the following as references:

- the functional behaviour approved in the previous application;
- the structural analysis of the base workbook;
- the operational analysis of rates and estimates;
- the profiling of product, stock, customer, location, zone, fuel and rate files;
- the difficulties identified in data import, reconciliation and administration.

The rebuild must not copy the workbook literally or assume that the previous code is correct. The objective is to retain useful behaviour, confirm business rules with evidence, and build a maintainable, secure, explainable and verifiable solution.

This document is an analysis and development plan. It does not approve rates, activate data or turn hypotheses into commercial rules.

## 2. Mandatory principles

1. **One active source per domain.** Products, stock, customers, locations, zones, fuel and rates must have identifiable versions and one explicitly active version.
2. **The workbook is a historical functional reference, not a production database.** It may be used to understand workflows and prepare comparisons, but it must not be a silent fallback.
3. **Data and rules must be separated.** Rates and their conditions must not be hard-coded in the interface or scattered across specific conditional logic.
4. **Every estimate must be explainable.** It must be possible to reconstruct which data version, zone, rate, conditions, minimums and surcharges produced the result.
5. **Validated does not mean active.** Upload, structural validation, reconciliation, approval, activation and verification are separate states.
6. **An unknown value does not equal zero.** An incomplete path must be marked as unresolved or pending, with a visible reason.
7. **Changes must be reversible.** Every data activation must allow a return to the last stable version.
8. **Security is enforced in the backend.** Permissions must not depend only on what the interface displays or hides.
9. **Anomalies are not removed automatically.** Duplicates, negative values, incomplete codes or missing references require classification and approved rules.
10. **Test behaviour before optimising it.** The initial priority is correct, traceable and repeatable rules.

## 3. What can already be treated as established

The following points are supported by the reviewed documents. They must be verified again against the original files and available code when the project begins, but they do not need to become general discovery questions.

### 3.1 Expected functional flow

- The application estimates shipments with one or more lines.
- Each line may originate from an authorised product or custom freight, where permissions and workflow allow it.
- The user needs to provide an authorised origin, destination, quantities, dimensions, weight, load type and applicable handling options.
- The application consolidates shipment quantity, weight and cubic volume.
- Eligible carrier and service combinations are evaluated separately.
- Results are presented as estimates, normally ordered by price, without confusing a calculated price with confirmed operational capacity.
- Saved estimates must respect customer, user, role and authorisation scope.

### 3.2 Actual calculation complexity

- A rate is not necessarily an isolated row: there may be an entry Rate Card that points to other rules or charges.
- Order, references, filters, breaks and units may affect the result.
- The calculation may include actual weight, volumetric weight, minimums, base charges, units, fuel, zones, overlength, tailgate, handling and other conditional charges.
- Rules may vary by customer, carrier, service, route, zone and load type.
- Carrier cost, margin and customer price are different concepts and must be modelled explicitly.

### 3.3 Condition of the available data

- Legacy Excel, modern Excel and CSV files exist.
- Some datasets are large, particularly zones and products, and require chunked processing and background tasks.
- Some codes that look numeric must be preserved as text so that leading zeros are not lost.
- There are exact duplicates, repeated keys with different values, and tables without a reliable business key.
- Relationships between stock, products, customers, locations, zones, fuel and rates are incomplete.
- Some values require business interpretation: negative rates, negative cubic volume, extreme quantities or weights, unusual states, and zero dimensions.
- Some rate expressions are procedural or complex and must not be executed directly from imported files.

### 3.4 Workbook limitations

- The workbook contains an interface, intermediate calculations, flattened data and a very large number of formulas.
- It depends on external sources for some data and contains broken internal references.
- It requests a full recalculation, and the available analysis does not certify its interactive results.
- Its structure helps explain the design, but it does not prove that every stored amount is current or correct.
- Reproducing its formulas cell by cell would create a solution that is difficult to maintain and diagnose.

## 4. Matters that are not yet certified

1. The actual state of the repository, database and deployed version.
2. Which behaviours in the previous application were tested end to end and which were only partially implemented.
3. The exact meaning of every rate field, expression, reference and unit.
4. The final commercial order of minimums, fuel, surcharges and margin for every applicable combination.
5. The recalculated functional behaviour of the workbook with all dependencies available.
6. The final policy for missing references, expired data or partially invalid sources.
7. Which operational exceptions must block an estimate and which should only show a warning.

## 5. Proposed scope for the first version

### Included

- user authentication and administration;
- separation between internal and external users;
- authorisation by customer, origin and estimate;
- customer, product, stock, location, carrier and service master data;
- file upload with staging, validation, reconciliation, activation and rollback;
- zone, rate and fuel versions;
- a typed and traceable rules engine;
- multi-line shipment creation;
- product selection and authorised custom freight;
- consolidation of weight and cubic volume;
- destination and zone resolution by service option;
- estimate calculation with breakdown;
- saving and retrieving estimates;
- audit of actions and changes;
- reconciliation and activation back-office;
- automated tests, observability and recovery procedures.

### Outside the initial scope

- direct integration with third-party APIs;
- automatic order or consignment creation;
- price lookup for external orders;
- immediate synchronisation with all existing systems;
- advanced packing optimisation;
- automatic replacement of unconfirmed operational decisions;
- removal of historical columns or data without a usage study.

These functions may be assessed after the calculation and master data are stable.

## 6. Proposed functional architecture

### 6.1 Identity and authorisation module

- Internal users with access to assigned customers.
- External users limited to their organisation, authorised origins and permitted estimates.
- Granular roles and permissions for uploading, reconciling, approving, activating, rolling back and estimating.
- Permission checks in every backend operation.
- Audit of sign-in, sensitive reads and administrative changes.

### 6.2 Master data module

- Customers and origin addresses.
- Products, physical attributes and stock relationships.
- Normalised locations while also preserving original text.
- Carriers and services.
- Zone rules by carrier and service.
- Fuel versions.
- Catalogue of units and load types.

Rows without a safe natural key must receive a technical identifier, without replacing or losing source identifiers.

### 6.3 Import and reconciliation module

Mandatory workflow:

1. Receive and immutably preserve the original file.
2. Calculate its hash and identify format, worksheet, encoding and schema.
3. Load it into staging without affecting active data.
4. Perform structural validation of headings, types and required fields.
5. Perform semantic validation of duplicates, relationships, currency, units and ranges.
6. Reconcile new, changed, ambiguous or missing values.
7. Correct individual records or compatible groups.
8. Preview the impact and exact set of changes.
9. Obtain approval and explicit activation by an authorised person.
10. Run post-activation tests.
11. Roll back to the previous version if verification fails.

The back-office must present actions as clear buttons or menus. Each row must display the original value, normalised value, existing value, status, reason and proposed action. Bulk corrections must only be enabled when every selected record supports the same safe transformation.

### 6.4 Rating engine

The engine must represent explicit rules rather than execute free-form text from files. Each rule must include, where relevant:

- source identifier and version;
- priority, sequence and reference to another rule;
- customer, carrier, service, origin, destination, zone, subzone or area;
- evaluated field, operator, value, range and unit;
- effective period and status;
- charge type;
- calculation basis;
- rounding rule;
- relationship with minimums, fuel and later charges;
- result classification: applicable, not applicable or unknown.

It must detect missing references, cycles, ambiguous paths and uninterpreted rules. A problem on one route must not invalidate independent options that can be certified.

### 6.5 Estimate service

For every request:

1. Validate the user, customer and authorised origin.
2. Validate and normalise the destination without silently changing the selection.
3. Validate shipment lines and their units.
4. Consolidate weight, cubic volume and quantities according to approved rules.
5. Determine eligible service options.
6. Resolve the specific zone for each option.
7. Select the active rate and fuel versions.
8. Traverse rules and references in order.
9. Calculate chargeable weight, base charges, minimums and surcharges.
10. Apply customer price and margin according to customer policy.
11. Return the estimate, warnings, eligibility and auditable breakdown.
12. Save a snapshot of inputs, sources and result.

A historical estimate must not change retroactively when a new data version is activated.

### 6.6 User interface

The known workflow will be retained as the baseline:

- selection of an authorised origin;
- destination search by suburb, state and postcode;
- one or more product lines;
- product selection or authorised custom freight;
- adding and removing lines;
- summary of quantity, weight and cubic volume;
- applicable handling options;
- a clear calculate action;
- carrier and service results ordered by price;
- visible estimate labels and operational warnings;
- saving and retrieving estimates according to permissions.

Visual improvements must focus on clarity, accessibility, contextual validation and error recovery, without unnecessarily redesigning a workflow already understood by users.

## 7. Phased work plan

### Phase 0 — Governance, access and baseline

**Objective:** ensure that the team works from identified sources and with clear owners.

**Activities:**

- appoint product, data, operational, security and commercial approval owners;
- inventory the repository, snapshots, database, deployments, files and documentation;
- calculate hashes and record dates for all sources;
- determine which version of the previous application was actually used;
- create a decision register and shared glossary;
- define separate development, test and production environments.

**Deliverables:** verifiable inventory, responsibility matrix, glossary, risk register and documentary baseline.

**Exit:** implementation does not begin until sources and approval authorities are identified.

### Phase 1 — Functional and operational discovery

**Objective:** turn implicit knowledge into demonstrable rules.

**Activities:**

- conduct guided sessions with the person responsible for the workbook and with operations;
- run real cases from beginning to end;
- record inputs, intermediate decisions and every result component;
- recalculate a controlled copy of the workbook with its dependencies available;
- identify which parts of the previous interface must be preserved;
- classify each rule as confirmed, inferred or unknown.

**Deliverables:** process map, rule catalogue, exception catalogue, permission matrix and initial set of reference cases.

**Exit:** critical rules for priority scenarios have evidence and an owner.

### Phase 2 — Data and import contracts

**Objective:** define how each source is received, validated, reconciled and versioned.

**Activities:**

- specify required and optional columns, aliases, types, keys and relationships for each file;
- define handling of variable worksheets, encoding, BOM, delimiters and legacy formats;
- agree rules for duplicates, blanks, zeros, negative values and extreme values;
- establish technical identifiers for stock and zones;
- prepare anonymised fixtures containing valid and problematic cases;
- define lifecycle states and activation permissions.

**Deliverables:** versioned contracts, data dictionary, quality rules, staging design and import test cases.

**Exit:** no field is imported without a type, meaning, traceability and error policy.

### Phase 3 — Technical and user-experience design

**Objective:** approve an architecture that supports the rules without reproducing workbook complexity.

**Activities:**

- design the domain model and relationships;
- design the typed rules engine;
- define versioning, atomic activation and rollback;
- design APIs and boundaries between interface, estimating, import and audit;
- create prototypes for estimating, reconciliation, preview and activation;
- perform threat, privacy and permission reviews.

**Deliverables:** approved architecture, data model, API specification, prototypes and security model.

**Exit:** the technical and visual walkthrough is approved before substantial development begins.

### Phase 4 — Platform foundation

**Objective:** implement the foundations without activating uncertified commercial rules.

**Activities:**

- configure repository, continuous integration, environments and secret management;
- implement identity, roles, customers and origins;
- implement audit and observability;
- implement original-file storage and staging;
- implement asynchronous chunked processing;
- implement versioning, approval, activation and rollback.

**Deliverables:** deployable test platform, access controls and base import pipeline.

**Exit:** technical, permission and rollback tests pass.

### Phase 5 — Importers and reconciliation

**Objective:** safely load all required sources.

**Recommended order:**

1. Customers and origins.
2. Locations.
3. Products.
4. Stock.
5. Carriers and services.
6. Zones.
7. Fuel.
8. Rates and references.

**Activities:**

- build one adapter per file contract;
- preserve original and normalised values;
- display blocking errors and warnings separately;
- implement safe individual and bulk reconciliation;
- produce duplicate and missing-reference reports;
- test large files, special characters and irregular legacy containers.

**Deliverables:** importers, quality reports, reconciliation back-office and automated tests using representative files.

**Exit:** each import is reproducible, auditable, atomic and reversible.

### Phase 6 — Rating engine and traceability

**Objective:** implement confirmed estimate paths first.

**Activities:**

- create a safe representation of conditions, references, units and charges;
- implement cycle and missing-reference detection;
- implement chargeable weight, breaks, base charges, minimums and approved rounding;
- implement fuel and surcharges according to confirmed bases and order;
- separate carrier cost, margin and customer price;
- produce both technical and readable explanations of each total;
- mark unknown paths without affecting independent routes.

**Deliverables:** versioned engine, calculation traces and test suite by rule and scenario.

**Exit:** each priority scenario matches its reference case or has an explained and approved variance.

### Phase 7 — Estimate and administration experience

**Objective:** complete the user workflow and administrative control.

**Activities:**

- implement multiple lines, product selection and custom freight;
- implement summary and contextual validation;
- display results, warnings and breakdowns according to role;
- save immutable estimate snapshots;
- implement authorised search and retrieval;
- complete reconciliation, approval and activation screens;
- conduct accessibility and usability tests.

**Deliverables:** complete workflow in the test environment and preliminary operating manuals.

**Exit:** representative users complete critical tasks without technical-team assistance.

### Phase 8 — Integrated validation and parallel operation

**Objective:** demonstrate that the new application is correct and operational.

**Activities:**

- run normal, boundary and exception cases;
- compare the recalculated workbook and operational results using the same data version;
- separate differences caused by data from differences caused by logic;
- test customer isolation and unauthorised access;
- test concurrency, volume, timing and partial failures;
- run restoration and rollback;
- operate in parallel without immediately replacing the current process.

**Deliverables:** validation report, resolved defects, accepted risks and recovery evidence.

**Exit:** a formal release decision is based on measurable criteria.

### Phase 9 — Production release and stabilisation

**Objective:** complete a controlled transition.

**Activities:**

- freeze and record the initial data versions;
- run migration and pre-release checks;
- train administrators and users;
- enable access for controlled groups;
- monitor errors, unknown estimates, differences and timing;
- retain rollback procedures during stabilisation;
- close outstanding matters and update canonical documentation.

**Deliverables:** production version, runbook, support matrix, metrics and post-release review.

**Exit:** stable operation, trained owners and accepted residual risks.

## 8. Priorities

| Priority | Work | Dependency | Expected outcome |
|---|---|---|---|
| P0 | Source inventory and authority | Access to materials | Verifiable baseline |
| P0 | Confirmation of critical rules | Real cases and owners | Approved specification |
| P0 | Security and customer isolation | Permission matrix | No cross-customer access |
| P0 | Staging, versioning, activation and rollback | Data contracts | Controlled production data |
| P0 | Traceable engine for priority scenarios | Confirmed rules | Explainable totals |
| P1 | Importers for every source | Approved contracts | Reproducible import |
| P1 | Individual and bulk reconciliation | State model | Less navigation and fewer errors |
| P1 | Saved and immutable estimates | Identity and engine | Reliable history |
| P1 | Automated testing | Reference cases | Detectable regression |
| P2 | Performance and advanced experience | Stable workflow | Efficient operation |
| P3 | External integrations | Stable product and approved scope | Additional automation |

## 9. Test strategy

### Data and import

- files with BOM, different encodings, delimiters and quotation marks;
- accented characters, apostrophes and line breaks;
- codes with leading zeros;
- variable worksheet names and approved alternate headings;
- exact duplicates, repeated keys and legitimately repeated rows;
- missing references;
- negative, extreme, blank and zero values;
- large files and interrupted processing;
- retrying the same file and hash detection;
- atomic activation and rollback.

### Rating engine

- values immediately below, at and above every boundary;
- actual weight greater than, equal to and less than volumetric weight;
- units by kilogram, unit, carton, pallet and consignment;
- base charge, minimum and additional units;
- fuel and every surcharge with true and false conditions;
- references with one or multiple stages;
- missing reference and cycle;
- not applicable, applicable and unknown rules;
- carrier cost, margin and customer price without double application;
- data-version changes without altering historical estimates.

### Security and audit

- external user attempting to access another customer;
- internal user without assignment;
- activation or rollback without permission;
- direct access to endpoints hidden in the interface;
- complete audit of upload, correction, approval, activation and estimate;
- protection of files, personal data and secrets.

### User experience

- valid, ambiguous and non-existent destination;
- authorised and unauthorised product;
- permitted and prohibited custom freight;
- multiple lines and line removal;
- visible validation at the location of the error;
- priced, ineligible and unknown results;
- reconciliation and return to the same point in the workflow.

## 10. Minimum production release criteria

- Every approved critical scenario has an automated test and business evidence.
- No unknown route is presented as a valid price.
- Active data versions are visible and traceable.
- Customer isolation passes negative authorisation tests.
- Every total can be explained through components and sources.
- Activation and rollback have been successfully tested.
- Importers support the agreed real formats and clearly reject unsupported formats.
- Saved estimates retain the input, result and versions used.
- No critical defects remain open and no high-severity defects lack documented acceptance.
- An operating manual, incident procedure, owners and monitoring exist.
- The process owner approves the functional scenarios and exceptions.

## 11. Principal risks and mitigation

| Risk | Consequence | Mitigation |
|---|---|---|
| Copying formulas without understanding them | Results that cannot be maintained | Reference cases and typed rules |
| Using old data as a fallback | Incorrect prices without warning | Explicit activation and visible blocking |
| Losing rate references or order | Incomplete calculation | Graph model, validation and traces |
| Interpreting zero as unknown | Undercharging | Explicit states and error policy |
| Partial import | Mixed versions | Staging and atomic transaction |
| Incorrect keys | Merged or duplicated records | Technical identifiers and reconciliation |
| Executable free-form expressions | Security and logic risk | Restricted parser or typed rules |
| Double margin or surcharge | Incorrect price | Separation of cost, price and charge basis |
| Cross-customer access | Security incident | Backend authorisation and negative tests |
| Difference between price and capacity | Incorrect operational promise | Eligibility state and warning |
| Dependence on one person | Loss of knowledge | Glossary, decisions and canonical documentation |

## 12. Recommended way of working with the person responsible for the workbook

Sessions must use concrete examples rather than abstract questions. Each case will record:

- representative customer and origin, anonymised where appropriate;
- complete destination;
- lines, quantities, dimensions, weight, volume and load type;
- special options;
- sources and versions used;
- expected carriers and services;
- selected zone and rules;
- step-by-step calculation;
- carrier cost, margin and customer price;
- warnings or need for operational confirmation;
- expected result and evidence.

Every decision must be recorded with its date, scope, owner and examples. If a rule applies only to a specific combination, it must not be generalised.

## 13. Questions that remain open

The following questions cannot be answered with certainty from the available documents and must be resolved before or during the initial phases.

### Data authority

1. **Question**

   For each type of information, which file or system must provide the correct data, and who must review and authorise its use in the application?

   **Answer provided**

   The complete files imported daily are the official sources.

   **Still to be confirmed**

   The person authorised to review or approve each data domain, and whether activation is manual or may occur automatically after all validations pass.

2. **Question**

   How frequently is each source updated, and which date or field determines its currency?

   **Answer provided**

   Every source is updated daily. Currency is determined by the file generation date and time. The most recently generated file becomes the current version only after successful import and validation.

   **Still to be confirmed**

   The exact location of the generation date and time: inside the file, in the filename or in a separate control record; and the rule for two files with the same generation time.

3. **Question**

   What policy applies when a source is expired, incomplete or late: block everything, block only affected routes, or allow an authorised exception?

   **Answer provided**

   The application must raise an alert and the file must be generated again from the source system.

   **Still to be confirmed**

   While the replacement file is being generated and processed, whether the application retains the last valid version, blocks affected estimates or blocks all related estimates; who receives the alert; and the age at which a file becomes expired.

4. **Question**

   Which files represent complete datasets and which are partial or temporary extracts?

   **Answer provided**

   Every file to be read is a complete dataset. Partial or temporary extracts will not be used. The complete customer file will be imported, but customers will be enabled progressively. The first customer will be enabled and stabilised before another customer is enabled.

   **Still to be confirmed**

   Who authorises each customer enablement, which readiness tests are required, and whether enablement may be limited by origin, service or user group.

5. What do the observed negative values, extreme values, zero dimensions and unusual postcodes mean?
6. **Question**

   When does a repeated row represent a duplicate that must be excluded, and when does it represent a legitimate line?

   **Answer provided**

   Potential duplicates must be flagged and reported for review. They must not be excluded, deleted or merged automatically. Some otherwise similar records may use an older classification code and a newer replacement code, so the reviewer must distinguish a genuine duplicate from a historical code, replacement, alias or valid coexistence.

   **Still to be confirmed**

   Whether an authoritative historical-code mapping exists, what happens to the older record after replacement, and who approves the classification.

7. **Question**

   Do Stock data and Products data `category` represent different domains? If so, what is the purpose of each one?

   **Answer provided**

   Products data contains the product master and product description. Stock data represents the quantity administered in the warehouse for the product. The datasets therefore have different purposes and must be related using the applicable product identifier.

   **Still to be confirmed**

   The specific business meaning of `category` in Products data and `category` in Stock data, whether they should match, and whether either field affects estimating, product selection or storage.

### Rate selection and traversal

8. Which exact fields in Rates data identify the first applicable Rate Card or rule, and which fields identify a rule that can only be reached by reference? Explain the roles of `master_rate`, `rate_no` and `run_rate` using a real example.
9. What is the exact meaning of `break`, `item_no`, wildcard, reference, type and customer price in Rates data?
10. When rules have the same sequence value, including equal `break` or `item_no`, or the relevant sequence field is blank, does physical file-row order affect evaluation?
11. When several rules match, does the system use the first match, highest priority, accumulation or another policy?
12. What should happen when a reference is missing, cancelled, expired or cannot be interpreted?
13. Which references may safely be ignored for one case, and which make the entire calculation path unknown?
14. Are valid cycles possible between Rate Cards, or must every cycle be treated as an error?

### Weight, volume and packing

15. For each carrier and service, what is the exact cubic conversion source field, factor, unit and rounding method?
16. How is cubic volume calculated when several units are packed together rather than travelling as separate items?
17. When is empty pallet weight or volume added, and what is the source of that value?
18. In Rates data or operational rules, what do `pal`, `pal1`, `pal2`, `pallet` and `lift` represent, what values may each field contain, and in which unit is each expressed?
19. Does Cubic Margin change the cubic volume used in the calculation, only the displayed value, or both? What is its permitted range, and who may change it?
20. Which dimensions, weights or load types require operational confirmation even when a rate can be calculated?

### Price composition

21. For each rate structure, what is the exact order of the base charge, variable rate, minimum, fuel and additional charges?
22. Which subtotal is used to calculate each percentage surcharge, and which components are excluded?
23. Does each rate source represent carrier cost, customer price or a value that already includes margin?
24. How is margin defined by customer and service, who may change it, and when does it become effective?
25. How are components and totals rounded: by line, by charge or only at the end?
26. Is tax excluded, shown separately or included at any stage of the customer price?
27. Which charges may accumulate, and which are mutually exclusive?

### Eligibility and commercial result

28. Which conditions determine that a service is eligible, in addition to the existence of a rate?
29. What are the legal and operational differences between an estimate, a saved estimate and a binding quotation?
30. How long is a saved estimate valid, and what happens if rates or fuel change before it is used?
31. Which users may view carrier cost, margin, customer price, technical breakdown and audit data?
32. Which warnings must prevent use of the result, and which allow continuation subject to confirmation?

### Products, stock and custom freight

33. Does stock availability limit product selection, or does Stock data only provide information?
34. Which source takes precedence when Products data and Stock data differ in description, weight, cubic volume or `category`?
35. In the stock files, what does an empty `serial_no` mean? Does it indicate that the product is not serial-controlled or that information is missing? When `serial_no` has a value, must it be unique to one stock unit, or may it legitimately occur in multiple rows? Which additional fields participate in its identity?
36. Which users and customers may use custom freight, and which fields are mandatory in that mode?
37. How are kits or grouped products handled: estimated as one set, expanded into components or based on actual packing?

### Locations and zones

38. Which source is authoritative when Zones data and the location master disagree?
39. How should suburb aliases, foreign locations, non-standard state values and short postcodes be handled?
40. Does a zone depend only on destination, or also on origin, service, load type or other attributes?
41. What policy applies when several zone rules match the same combination?

### Migration and operation

42. Which historical data from the previous application must be migrated, and which may be retained only as a searchable archive?
43. Which version of the previous application was actually used, and is there a database or deployment that must be preserved as evidence?
44. What maximum volume of estimates, users and files is expected over the next several years?
45. What is the target time for calculating an estimate and processing each file type?
46. How long must original files, data versions, audit records and estimates be retained?
47. Who may approve an activation, and must there be separation between the person who uploads, reconciles and activates?
48. Which emergency procedure is authorised if an active version produces incorrect customer prices?

## 14. Requested next decision

Before development begins, it is recommended that the following be approved:

1. the scope of the first version;
2. the owners and authorities for each source;
3. the priority scenarios to be used as references;
4. the schedule of sessions needed to resolve open questions;
5. the acceptance criteria and production release policy.

Once these five points are agreed, the team can turn this plan into a backlog, estimates and delivery schedule without introducing unconfirmed commercial rules.
