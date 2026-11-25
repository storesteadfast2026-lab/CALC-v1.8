# Context for Rebuilding the Freight Estimating Application

## 1. Purpose

This document provides the shared context needed to rebuild the freight estimating application from the ground up. It is intended to accompany `PLAN.md` and to help product, operational, data and technical reviewers work from the same understanding.

The application existed previously. The new implementation must preserve useful and approved behaviour, resolve known gaps, and apply sound practices for security, imports, reconciliation, rating, traceability, testing and rollback.

The previous application, workbook and historical values must not be assumed to be complete, current or correct without evidence.

## 2. Reference material

The available context consists of:

- documentation of the previous application's expected frontend and back-office behaviour;
- structural analysis of the reference workbook;
- structural profiling of customer, product, stock, postcode, zone, fuel and rate files;
- an operational note describing Rate Card and estimate concepts;
- answers confirmed during review of the work plan.

Supplementary operational information must be identified only as an **operational note**. Its private origin must not be disclosed or inferred. An operational note provides context but does not automatically constitute an approved commercial rule.

## 3. Application objective

The application must allow authorised internal and external users to prepare freight estimates using current operational data.

The expected workflow includes:

- selecting an authorised customer and origin;
- selecting a destination by suburb, state or territory, and postcode;
- adding one or more shipment lines;
- selecting an authorised product or entering custom freight where permitted;
- entering quantity, dimensions, weight, load type and relevant handling options;
- reviewing shipment weight and cubic-volume totals;
- calculating eligible carrier and service options;
- displaying estimates and operational warnings;
- saving and retrieving estimates according to permissions.

Internal users must only access assigned customers. External users must only access their own organisation's authorised data and estimates.

## 4. Meaning of an estimate

An estimate may depend on:

- customer and authorised origin;
- destination and carrier-specific zone;
- carrier and service eligibility;
- actual weight, volumetric weight and chargeable weight;
- product, unit, carton, pallet or consignment information;
- base charges, variable rates and minimum charges;
- fuel surcharge;
- tailgate, handling, remote-area, overlength, overweight or other conditional charges;
- carrier cost, customer margin and customer price.

A calculated price does not by itself prove that the carrier can operationally accept the shipment. Oversized, non-stackable or specially handled freight may still require operational confirmation.

An unresolved condition must be visible. It must not be silently converted to zero.

## 5. Workbook role and limitations

The workbook is a historical functional reference. It contains:

- an estimate-entry interface;
- intermediate shipment calculations;
- carrier and service totals;
- product and stock information;
- suburbs and zones;
- rates, fuel and surcharges;
- supporting import and preparation worksheets.

The workbook helps explain the user flow and calculation structure. It must not be reproduced cell by cell as the application architecture.

Its limitations include:

- a very large number of formulas;
- external file and data dependencies;
- broken defined-name references;
- full-recalculation requirements;
- flattened rate and zone tables that may not expose the complete source-system rule traversal.

The workbook is not an approved fallback for production rates, zones or fuel.

## 6. Official daily sources

The complete files imported daily are the official sources for:

- customers;
- products;
- stock;
- postcodes and locations;
- zones;
- fuel;
- rates.

Partial or temporary extracts will not be used.

The file generation date and time determine which version is newer. A newer file must still be imported and validated successfully before it becomes active.

If a file is late, incomplete, expired or invalid:

- the application must raise an alert; and
- the file must be generated again from the source system.

It remains necessary to confirm what the application does while the replacement file is being generated, where the authoritative generation timestamp is stored, and who approves each data domain.

## 7. Import and activation lifecycle

Each official source must follow a controlled lifecycle:

1. Preserve the original file unchanged.
2. Record its hash, generation time, receipt time and import time.
3. Load records into a staging area.
4. Validate file structure, headings and types.
5. Validate relationships, duplicates, values and rules.
6. Reconcile new, changed, ambiguous and missing records.
7. Preview the exact effect of the proposed changes.
8. Obtain authorised approval.
9. Activate the complete version atomically.
10. Verify representative estimates.
11. Roll back if post-activation verification fails.

Uploaded, structurally valid, reconciled, approved, active and verified are different states.

## 8. Complete imports and progressive customer enablement

The complete Customers data file will be imported, but customers will be enabled progressively.

Importing a customer does not mean enabling that customer for estimates.

The first customer will be enabled and stabilised before another customer is enabled. Records for customers that are not yet enabled must be retained but must not be available for estimates.

Customer enablement must be explicit, permission-controlled, auditable and reversible.

The approval owner, readiness criteria and possible enablement scope by origin, service or user group remain to be confirmed.

## 9. Products and stock

Products data contains the product master and product description or attributes.

Stock data represents the quantity administered in the warehouse for those products.

The two datasets have different purposes and must be related using the applicable product identifier.

Both datasets contain a field named `category`, but the observed values do not match. It remains necessary to confirm:

- the meaning of Products data `category`;
- the meaning of Stock data `category`;
- whether they should ever match;
- whether either field affects product selection, storage or estimating.

## 10. Duplicate and historical-code handling

Potential duplicates must be flagged and reported for review. They must not be deleted, merged or excluded automatically.

Similar records may differ only because an older classification code was replaced by a newer code. A reviewer must distinguish:

- exact duplicate;
- legitimate repeated line;
- historical code;
- replacement code;
- alias;
- valid coexistence;
- unresolved case.

The application must retain the source evidence and audit the decision, reviewer, time and justification.

It remains necessary to confirm whether an authoritative historical-code mapping exists and what happens to the older record after replacement.

## 11. Source identifiers and fields

Technical field names must remain exactly as they appear in the source. They must not be translated or renamed in documentation or questions.

Relevant examples include:

- `master_rate`;
- `rate_no`;
- `run_rate`;
- `break`;
- `item_no`;
- `filter_field`;
- `serial_no`;
- `category`;
- `pallet`;
- `lift`.

When the same field name occurs in more than one source, the applicable file or dataset must also be identified.

## 12. Stock `serial_no`

The stock files contain populated and empty `serial_no` values.

An empty `serial_no` must not automatically cause two rows to be treated as duplicates. Its business meaning remains to be confirmed. It may represent a product that is not serial-controlled, missing information or grouped quantity.

It also remains necessary to confirm whether a populated `serial_no` must identify one stock unit or may legitimately occur in multiple rows with other identity fields.

## 13. Rates and Rate Cards

The workbook contains a flattened `RATES` representation for lookup. This does not prove how the complete daily Rates data uses references and ordering.

The source Rates data includes fields such as:

- `master_rate`;
- `rate_no`;
- `run_rate`;
- `break`;
- `item_no`;
- `filter_field`;
- `from`;
- `greater`;
- `upto`;
- `to`;
- `unit`;
- `rate`;
- `basic_charge`;
- `min_charge`.

The application must not execute free-form `filter_field` content directly.

If the new application interprets the complete Rates data directly, it must establish:

- how the first applicable Rate Card or rule is selected;
- how `run_rate` references are followed;
- whether physical row order matters when sequence fields match or are blank;
- what happens when multiple rules match;
- how missing, expired, cancelled or cyclic references are handled;
- how traversal ends.

An affected path may be classified as applicable, not applicable or unknown. A problem on one path must not automatically block independent paths that are fully resolved.

## 14. Weight, cubic volume and packing

The rating engine may compare actual weight with volumetric weight to determine chargeable weight.

The cubic conversion factor, unit and rounding may vary by carrier and service. These details must be extracted from the available workbook and previous code where possible, then confirmed when ambiguous.

The application must also establish:

- how multiple units are treated when packed together;
- when empty pallet weight or volume is added;
- whether rounding occurs per line or after shipment totals;
- whether a minimum chargeable weight applies;
- whether Cubic Margin changes the calculation, display or both.

Fields such as `pal`, `pal1`, `pal2`, `pallet` and `lift` must not be interpreted until their meaning, permitted values and units are confirmed.

## 15. Price composition

The application must distinguish:

- carrier cost;
- customer margin;
- customer price.

It must not apply margin twice or assume that every imported `rate` represents the same commercial concept.

For each supported rate structure, the following must be explicit:

- base charge;
- variable rate and unit;
- minimum charge;
- fuel surcharge base;
- additional surcharges;
- order of application;
- rounding;
- tax treatment;
- effective version.

## 16. Traceability and saved estimates

Every estimate must retain enough information to reproduce and explain its result, including:

- user input;
- customer and origin;
- destination;
- shipment lines and totals;
- active data versions;
- resolved zone;
- evaluated rules and references;
- actual, volumetric and chargeable weight;
- charge components;
- warnings and unresolved conditions;
- calculation time and engine version.

A saved estimate must not change retroactively when new source versions are activated.

## 17. Security and audit

Permissions must be enforced in the backend.

The audit trail must cover:

- source-file receipt and import;
- validation results;
- reconciliation changes;
- duplicate classification;
- approval and activation;
- rollback;
- customer enablement;
- estimate creation and retrieval;
- role and permission changes.

An imported record must not automatically create active users, permissions, customers or products.

## 18. Initial delivery boundary

The initial application includes identity, permissions, master data, imports, reconciliation, activation, rollback, rating, estimates, saved estimates, audit, testing and controlled customer enablement.

The following remain outside the initial scope unless separately approved:

- direct carrier or third-party APIs;
- automatic order or consignment creation;
- external-order price lookup;
- immediate synchronisation with every external system;
- advanced packing optimisation.

## 19. Relationship with `PLAN.md`

`PLAN.md` defines the work phases, architecture, tests, acceptance criteria, risks and open questions.

Confirmed answers are shown within the original questions as **Answer provided**. Any unresolved portion of an answered question is shown as **Still to be confirmed**.

No unresolved point should be converted into a commercial rule without evidence and approval.
