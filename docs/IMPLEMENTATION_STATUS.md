# Calc v1.8.01 implementation status

Last updated: 2026-11-20, Australia/Adelaide.

## Working application

- Django application: `http://127.0.0.1:8018/`
- Health endpoint: `http://127.0.0.1:8018/health/`
- Readiness endpoint: `http://127.0.0.1:8018/ready/`; it returns HTTP 503 until the database is reachable and all migrations are applied.
- Authentication and customer-scoped access are enforced by the backend.
- STH customer, origin, calculator options, products and Australian postcodes are loaded.
- The calculator returns operational estimates for eligible STH products.
- Software version `v1.8.01` is read from `app/VERSION` and is visible on calculator and Django login/header surfaces.
- Customer quote responses expose selling price only; internal cost components are enforced by the backend role.
- Internal quote results record the exact operational workbook and fuel file identifiers, filenames and SHA-256 hashes.
- Preselected SKU calculations always use server-owned product type, dimensions, weight and cubic values; request values cannot override them. Active Products with incomplete physical data or a cubic-versus-dimensions difference at or above the Client's configured confirmation factor are also rejected server-side and routed to Steadfast confirmation.
- FTP-drop client/file mappings are enabled in Django Admin and processed together under one shared Australia/Adelaide schedule. The initial schedule is 08:00 Monday-Friday. The scheduler creates immutable, SHA-256-deduplicated source snapshots and audit events only; it does not activate operational data.

## Active operational data

- Products: 379 STH products are active. On 2026-11-19, the 80 eligible STH source-only rows from Product Master #1 were explicitly applied from the current Product Master; audit batch `3643b570c58e4dfda7f275f58296c8bc` records 80 creates, 0 updates and 0 deletes. The remaining 63 source-only products require Steadfast confirmation and none is eligible for Apply.
- Postcodes: 18,099 Australian rows activated from `postcodes.xls` using ADD_ONLY.
- Operational workbook baseline: `uploaded_data/reference/STH_LIVE_BASELINE_20260709_152102.xlsx`.
- Baseline SHA-256: `AFA74C59E585A3589DAEC2F1FD761AFF97B588AA103738BD14615288B6401981`.
- Operational rows loaded without replacing product, postcode or reconciliation history:
  - 10 client carrier configurations;
  - 109,479 freight zones;
  - 5,550 flattened freight rates;
  - 5 tailgate charge rows;
  - 5 STH/TEAMEX overlength bands.
- Fuel: `fuel.xls` is ACTIVE; 19 valid rows, 6 matching configurations updated.
- The three unmatched configured cards are preserved rather than treated as zero.

## Source staging

- `rates_all.xls`: 8,727 raw rate-card lines stored for comparison only.
- `zones.csv`: 50,444 rows for the six demonstrated routes stored for comparison only.
- Raw rate-card staging does not silently replace the operational flattened tables.
- Fourteen missing raw Rate Card references remain recorded for review.

## Verification

- End-to-end customer login and API calculation verified with `cust1`, STH and active SKU `20012138`.
- Adelaide SA 5000 returned STEA, COCHRN, KTI and TEAMEX estimates.
- End-to-end role check verified that `cust1` receives no cost breakdown and `user1` receives source provenance.
- The historical 20-case Excel battery is not an acceptance gate for the new catalogue:
  19 cases reference products excluded by current eligibility rules and the expected amounts use historical fuel.
- The previous v1.7 audit remains reference evidence, not a production certification: 67,394 Excel cases were compared and 135 difference rows were documented.

## Known limitations before production approval

- Resolve or formally confirm the 63 remaining STH source-only products before any Apply: 56 have missing or partial dimensions, 2 (`J301-1661001-220` and `MAXI100`) have usable dimensions but lack positive weight or cubic, and 5 (`H4543`, `J201-4010000`, `J201-4020000`, `J213-1041000`, `J401-4500000`) have a recorded cubic volume that differs from length × width × height by a factor of 10 or more. Until corrected in the Product Master, the app directs users to Steadfast Contact Center or Customer Service instead of quoting them.
- Before production, resolve or formally confirm the 71 Products in the exportable physical-data issue report: 63 source-only Product Master rows and 8 active operational Products. The report includes the SKU, issue category, current Product Master values and protected correction fields. The same corrected `.xlsx` is accepted through a validated upload that first creates correction-round drafts; operational Products change only after the existing separate Preview/Apply confirmation. Contact Center routing does not remove a Product from the report. The reporting and round-trip workflow are implemented, but no correction has been applied.
- Resolve or formally accept the remaining raw rate-card references and ambiguous charge expressions.
- Define the operational error-notification channel, external monitoring destination, retention and deployment secrets for the target environment. Microsoft Teams is not used. Local liveness/readiness probes are implemented.

## Rollback

The pre-operational database backup is:

`uploaded_data/backups/calc_v18_pre_operational_20261118.dump`

Do not restore it over the current database without explicitly confirming the target database and taking a newer backup first.
# Latest continuation — weekly estimate validity

- Saved estimates now persist an explicit Monday-to-Sunday price-validity window.
- History lists apply each client's configurable `visible_history_days` window (14 days by default).
- Expired estimates remain immutable and viewable by authorised users, with warnings in history, print/PDF, email and duplicate-as-new flows.
- Creating a new estimate from an old one still requires recalculation against current rates.
- Every saved estimate creates an immutable `FREIGHT_ESTIMATE_SAVED` audit event containing the reference and validity dates.
- Migration `saved_estimates.0003_savedestimate_validity` is applied to the operational database.
- Automated verification now passes 611 tests with 4 intentional skips.
- The owner approved the 80 eligible STH Product Master rows on 2026-11-19. Product reconciliation audit event 23 and batch `3643b570c58e4dfda7f275f58296c8bc` record 80 creates, 0 updates and 0 deletes; all 80 are active and the operational STH Product count is now 379.
- Browser walkthrough verified the `cust1` customer and `user1` internal experiences. An unsaved Adelaide 5000 / SKU 20012138 calculation returned four options.
- The results interface was restored to the compact legacy presentation requested by the owner: carrier, service and estimate only for every calculator role. Cost components and source provenance remain server-side for audit and verified snapshots, and are not rendered in the calculator.
- A read-only `generate_acceptance_matrix` command now produces reproducible JSON and Markdown business-review cases from active Products and current operational rates. It explicitly marks every case pending business acceptance and records source provenance and component explanations without changing operational data.
- The first STH matrix generated seven representative cases: six returned eligible carrier results and the Hobart high-cubic/tailgate case remained unresolved. Its per-carrier diagnostics distinguish missing zones/rates and disabled tailgate coverage rather than treating the absence of a quote as zero.
- The project owner approved the seven-case STH acceptance evidence on 2026-11-18. The immutable approval record pins the Markdown and JSON reports by SHA-256 and explicitly accepts Hobart as a no-quote outcome, not a zero-price quote.
- Owner clarification on 2026-11-18: references to notifying the “team” mean the operational staff, not Microsoft Teams. No Microsoft Teams integration is required or configured; the eventual notification channel remains to be selected.
- Operational probes now separate liveness (`/health/`) from readiness (`/ready/`). Docker waits for PostgreSQL health before starting Django and monitors Django through the readiness endpoint; responses expose no connection or migration details beyond safe status labels.
- The STH rate-source review now inventories unsupported or source-dependent expressions by reason, charge/rule and example card/source row. Against the retained `rates_all.xls`, it reports all 363 affected catalogue rows in 165 groups: 352 unrecognised-expression rows and 11 rows dependent on unavailable `driver_zones.type`. The screen explicitly labels this as catalogue-wide structural evidence: it neither proves route impact nor activates the raw source or changes quote prices.
- A paired read-only Rates and Zones diagnostic is available from the STH Rates review. It pins both registered source IDs and hashes, reports missing card references, compares CSV zones with demonstrated base-price zones, and summarises synthetic case outcomes and unresolved conditions per carrier without changing operational tables.
- Missing Rate Card references are now classified by structural reachability from each of the six configured STH carrier roots. Every missing target retains its referring card and source row. In the retained source, 13 of 14 are linked structurally: 11 from the STEA root (`277`, `473`, `630`, `763`, `867`, `919`, `1171`, `1330`, `1348`, `1792`, `1898`), `1524` from TEAMEX and `1594` from TFMX. Card `1606` is not reachable from the six roots. This graph follows links without evaluating conditions—especially the unconfirmed STEA customer selection—so it prioritises investigation without claiming commercial applicability.
- Explicit customer selectors further reduce the STH priority: all 11 STEA missing targets select other customer codes, not `STH`. The read-only parser now safely recognises the exact state-exclusion expression attached to TFMX `1594`: the missing card is conditionally reachable outside NT and WA and is encountered in 624 synthetic coverage evaluations. TFMX also retains 744 synthetic evaluations with an unresolved `Residential Fee` condition (`jobs.ins_code`). The remaining priority raw-source gaps are therefore `1524` (`driver_zones.type` is absent from Zones) and the missing card content for `1594`; `1606` remains disconnected from the six STH roots. Counts are diagnostic evaluations, not shipments or proof of commercial applicability. This classification does not activate the raw sources or change operational quote logic.
- The paired diagnostic now presents a compact STH-priority summary and exports UTF-8 CSV evidence pinned to both source IDs and SHA-256 hashes. It includes missing targets, review classifications, referring cards/rows, customer scope, parser limitation, expression and per-carrier coverage; source text is neutralised against spreadsheet-formula injection.
- A pinned source investigation (`reports/rate_diagnostics/sth_missing_rate_cards_20261118.md`) confirms that neither the 15,338-row expanded Rate Table nor the v1.7 Rates source contains complete master cards `1524` or `1594`. The v1.7 source retains the same 14 missing references and differs from the current 8,727-row source in only three rate values; it is not an authorised fallback.
- Before the configured fallback was introduced, 143 STH Product candidates were blocked as new SKUs without a complete primary dimension triplet; there were no invalid or duplicate rows in that set. Product Master comparison shows reason summaries and exports source-hash-pinned UTF-8 CSV evidence while neutralising spreadsheet-formula text.
- A read-only comparison with the pinned historical workbook found positive `SKUs` dimensions for 81 of the 143 blocked products. Of those, 52 also match the current Product Master weight and cubic within tolerance and carry no workbook `M3ERROR`/`KGERROR` flag; they are stronger manual-review candidates, not approved corrections. The remaining 62 have no positive historical dimensions. No historical value is applied automatically or treated as current source authority.
- Product dimensions now support a per-Calculator-Customer fallback source when all three primary dimensions are zero or missing. The supported alternatives are `outer`, `inner` and `piece`; primary dimensions always take precedence and a partial primary triplet is never silently replaced. Migration `clients.0005` configures STH to use `outer`. The cubic-versus-dimensions confirmation factor is also configurable per Calculator Customer in Django Admin; migration `clients.0006` defaults it to `10`, including for STH. These settings change preview resolution only; they do not themselves Apply or activate any Product.
- Calculator Product search now exposes 63 current STH source-only products as non-calculable notices sourced read-only from the current validated Product Master: 56 with missing or partial dimensions, 2 with missing positive weight or cubic, and 5 whose cubic volume differs from length × width × height by a factor of 10 or more. Selecting one clears physical values, prevents calculation and directs the user to call Steadfast Contact Center or Customer Service for an accurate quote. Updating the Product Master physical values causes the application to re-evaluate the product; there is no hard-coded SKU blocklist. This does not create or activate a blocked Product. `BRH4443` was applied from the current Product Master with the configured STH `outer` fallback dimensions 4.70 × 0.75 × 1.05 m, weight 1750 kg and cubic 3.701 m³.
- The same customer-service rule now protects active operational Products in both Product search and the server-side calculation request. The current STH operational data contains 8 affected active Products: `CRATE01` has cubic `0`, while `J113-1060000A`, `J121-1213000`, `J213-1042000`, `J218-1210000`, `M245-25A24013`, `RAL2002` and `SB40-MP-24-3PH` exceed STH's configured factor `10`. Their stored dimensions and other values were not changed.
- Django Admin correction rounds now export one Product-issue workbook covering all 71 current problems. Staff can enter corrected physical values only in the marked fields, confirm a row and upload the same workbook for validation. The upload verifies the Product Master source hash and every immutable row identity, previews the intended corrections, and saves drafts only. Source-only rows are staged from the same validated Product Master when selected; their Products are created only by a later explicit correction-round Apply. The current report contains 56 unknown-dimension rows, 12 large-difference rows and 3 incomplete-physical-data rows.

## NetOz NGINX security assessment — 2026-11-19

- CVE-2026-123007 was verified against current NGINX/F5, Ubuntu and Debian advisories. It affects NGINX configurations using HTTP/2; upstream fixed releases are 1.30.7 stable and 1.31.9 mainline.
- The initial OpenSSH key was not the identity used by the working PuTTY session. After reusing the correct PPK identity through Plink, the remote assessment was completed.
- The VM and its application containers contain no NGINX instance. Public HTTPS is terminated by host Caddy 2.11.7, managed by the root-owned NetOz `nexusd` agent, and proxied to Gunicorn at `127.0.0.1:38000`.
- CVE-2026-123007 is specific to NGINX HTTP/2 and is not applicable to the verified Caddy-to-Gunicorn serving path. No operational remediation was required or applied.
- HTTPS login and a referenced static CSS asset passed over HTTP/2. The deployed v1.6 application does not expose the newer v1.8 `/health/` or `/ready/` endpoints.
- PostgreSQL, containers, images, persistent volumes, credentials and proxy configuration were not changed.
- Initial access evidence is retained in `docs/security/NETOZ_CVE-2026-123007_ASSESSMENT_1119.1103.md`; the verified closure is `docs/security/NETOZ_CVE-2026-123007_CLOSURE_1119.1126.md`.

