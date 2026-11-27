# Graph Report - app  (2026-11-27)

## Corpus Check
- 300 files · ~148,724 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 32 file(s) not represented in the graph (top: .csv 20, .css 6, (none) 3)

## Summary
- 3334 nodes · 9942 edges · 190 communities (93 shown, 97 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 763 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c68c7ac8`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Product
- calculator.py
- django_db
- admin_reconciliation.py
- FTPPostcodesImportTests
- fuel.py
- Client
- snapshots.py
- FuelXlsFlowTests
- re
- GlobalStockMasterTests
- imports/admin.py
- ProductReconciliationWorkspaceTests
- global_stock_master.py
- clients/models.py
- PostcodesReviewItemForm
- authentication_gateway/admin.py
- ExternalDataFile
- saved_estimates/views.py
- SourceImportError
- product_issue_report.py
- load_source
- walk_case
- freight/views.py
- ratecard_compare.py
- engine
- product_reconciliation.py
- import_customers
- validate_excel_battery.py
- ProductStockSourceTests
- rate_source_load.py
- ChainResolutionTests
- operational_test_runner.py
- ValidationError
- SavedEstimateTests
- django_apps
- generate_acceptance_matrix.py
- imports/models.py
- correction_memory_export.py
- load_rehearsal
- STHUserAdmin
- operational_ratecards.py
- authentication_gateway/views.py
- ftp_automation.py
- create_audit_event
- classify
- ProductMaster
- Command
- django_db_models
- pdf_export.py
- StockMasterAdmin
- ProductMasterReadOnlyReconciliation
- destinations
- FreightUserAccessTests
- ExternalDataFileAdmin
- postcodes_apply.py
- is_django_administrator
- CalculatorCustomerEnableTests
- overlength_fee
- apply_approved_postcodes
- emailing.py
- xlsx_reader.py
- validate_sth_rate_sources.py
- .handle
- FtpImportScheduleAdmin
- RatecardUploadAdminMixin
- scan_ftp_inbox
- ratecard_walk.py
- ProductRejectedRowsBulkReview
- ExternalDataReviewItemInline
- FtpImportScheduleAdminTests
- ProductCorrectionBulkUiTests
- ProductSourceRejectedRowAdmin
- ProductMasterAdmin
- ProductFileAdapterTests
- RatecardUploadTests
- load_cases
- ExpressionTests
- test_ratecard_walk.py
- FtpImportConfigurationAdmin
- FreightCalculator
- validate_product_master
- FtpImportConfiguration
- Customer
- ratecard_chain.py
- test_ratecard_chain.py
- read_zones
- ProductClientIdentityTests
- clients/admin.py
- ImportReconciliationExceptionAdmin
- CustomerSection
- sync_postcodes_review_items
- CompareError
- SavedEstimate
- CalculatorLoginSecurityTests
- CalculatorVisualContractTests
- ratecard_operational.py
- AuditEventAdmin
- CalculatorLoginFlowTests
- PostcodesAdminPresentationTests
- CommandTests
- SweepTests
- estimate_actions.js
- middleware.py
- FreightRequest
- FtpImportSchedule
- PostcodesApplyAdminMixin
- ratecard_coverage.py
- CalculatorAuthenticationForm
- CalculatorUserProfile
- Command
- StockMaster
- HashAndCommandTests
- ReadinessCheckTests
- OperationalRateEngineQuoteTests
- Command
- ValidateSourcesTests
- ExceptionAdminImportTests
- ProductAdmin
- carriers/admin.py
- validate_stock_master
- estimate_email.js
- FakeSheet
- Case
- HealthCheckTests
- locations/admin.py
- check_zones
- postcodes_review_compact.js
- persist_exception_evidence
- _teamex_weight_break
- ImportReconciliationException
- ProductKitComponent
- AccessManagementCommandTests
- Command
- .missing_reference_details
- CarrierAdmin
- AcceptanceMatrixCommandTests
- Command
- 0005_client_dimension_fallback_source.py
- Command
- GlobalStockSourceRow
- _best_alias_candidate
- SeedValuesTests
- HistoricalMatchSelect
- PostcodesReviewControlsField
- PostcodesReviewControlsWidget
- 0003_restore_client_sku_identity.py

## God Nodes (most connected - your core abstractions)
1. `Client` - 192 edges
2. `ExternalDataFile` - 173 edges
3. `Product` - 91 edges
4. `create_audit_event()` - 81 edges
5. `ExternalDataFileAdmin` - 72 edges
6. `SourceImportError` - 71 edges
7. `Customer` - 60 edges
8. `ClientCarrierConfig` - 57 edges
9. `ProductReconciliationWorkspaceTests` - 53 edges
10. `GlobalStockMasterTests` - 52 edges

## Surprising Connections (you probably didn't know these)
- `_calculator_client_field()` --uses--> `Client`  [INFERRED]
  apps/authentication_gateway/forms.py → apps/clients/models.py
- `FreightCalculatorAdminForm` --uses--> `FreightCalculator`  [INFERRED]
  apps/clients/admin.py → apps/clients/models.py
- `EnableCalculatorCustomerForm` --uses--> `Customer`  [INFERRED]
  apps/clients/admin.py → apps/clients/models.py
- `ClientAdmin` --uses--> `Customer`  [INFERRED]
  apps/clients/admin.py → apps/clients/models.py
- `CustomerAdmin` --uses--> `Customer`  [INFERRED]
  apps/clients/admin.py → apps/clients/models.py

## Import Cycles
- None detected.

## Communities (190 total, 97 thin omitted)

### Community 0 - "Product"
Cohesion: 0.07
Nodes (23): Command, Command, operational_product_contact_message(), product_contact_notices(), cubic_dimension_confirmation_factor(), cubic_dimension_difference_factor(), _decimal(), has_large_cubic_dimension_difference() (+15 more)

### Community 1 - "calculator.py"
Cohesion: 0.08
Nodes (16): chargeable_weight(), excel_weight_break(), FreightCalculatorService, _is_teamtas_general_code(), _is_teamtas_general_config(), _is_teamtas_general_rate(), _machipe_mipec_weight_break(), resolve_weight_break_for_config() (+8 more)

### Community 2 - "django_db"
Cohesion: 0.03
Nodes (41): Migration, Migration, Migration, Migration, Migration, Migration, Migration, Migration (+33 more)

### Community 3 - "admin_reconciliation.py"
Cohesion: 0.12
Nodes (29): correction_table_fields(), filter_correction_rows(), ProductCorrectionDecision, Meta, ProductCorrectionRound, apply_correction_round(), autosave_correction_field(), bulk_dimension_candidates() (+21 more)

### Community 4 - "FTPPostcodesImportTests"
Cohesion: 0.07
Nodes (14): Command, Command, Command, activate_postcodes_file(), _decode(), parse_postcodes_rows(), PostcodesImportError, _read_file_bytes() (+6 more)

### Community 5 - "fuel.py"
Cohesion: 0.05
Nodes (40): Command, activate_fuel_file(), build_validation_summary(), calculate_sha256(), compare_with_rates_all(), create_downloaded_fuel_file(), decode_csv_bytes(), default_fuel_source_url() (+32 more)

### Community 6 - "Client"
Cohesion: 0.07
Nodes (27): Carrier, Meta, CarrierService, Meta, ClientCarrierConfig, Meta, Client, Meta (+19 more)

### Community 7 - "snapshots.py"
Cohesion: 0.13
Nodes (17): FromAddress, Meta, build_freight_request(), _json_safe(), normalise_displayed_results(), recalculate_snapshot(), serialise_request(), serialise_results() (+9 more)

### Community 8 - "FuelXlsFlowTests"
Cohesion: 0.18
Nodes (5): ExternalDataFileAdminForm, Meta, card_line(), catalogue(), FuelXlsFlowTests

### Community 9 - "re"
Cohesion: 0.19
Nodes (5): Command, inspect_exception_evidence(), RegistryInputError, _required_digest(), _sha256()

### Community 11 - "imports/admin.py"
Cohesion: 0.08
Nodes (18): CalculatorAccessDenied, FetchFuelForm, ProductSourceRejectedRowReviewForm, Meta, SourceUploadForm, Command, ProductSourceRejectedRow, Meta (+10 more)

### Community 12 - "ProductReconciliationWorkspaceTests"
Cohesion: 0.06
Nodes (25): ProductReconciliationDecision, Meta, ProductReconciliationRule, Meta, apply_product_reconciliation(), build_product_apply_plan(), create_recommended_product_drafts(), _json_value() (+17 more)

### Community 13 - "global_stock_master.py"
Cohesion: 0.14
Nodes (13): authorised_stock_client(), _customer_map(), customer_resolution_summary(), _decimal(), _parse(), _reference_values(), _resolve_customer(), _safe_raw_data() (+5 more)

### Community 15 - "PostcodesReviewItemForm"
Cohesion: 0.11
Nodes (5): PostcodesReviewItemForm, Meta, classify_postcodes_source_action(), PostcodesHistoricalDropdownTests, PostcodesSourceAuthorityScreenTests

### Community 16 - "authentication_gateway/admin.py"
Cohesion: 0.11
Nodes (9): CalculatorProfileStatusFilter, _calculator_client_field(), CalculatorUserProfileAdminForm, Meta, PrimaryAccessFieldsMixin, STHUserChangeForm, Meta, STHUserCreationForm (+1 more)

### Community 17 - "ExternalDataFile"
Cohesion: 0.12
Nodes (13): ExternalDataFile, Meta, ExternalDataReviewItem, Meta, build_validation_summary(), _existing_origin_label(), _created_row_for_source(), _created_row_is_live_source() (+5 more)

### Community 18 - "saved_estimates/views.py"
Cohesion: 0.15
Nodes (20): calculator_access_required(), wrapped(), get_calculator_profile(), can_export_estimates(), estimates_for_user(), estimates_in_visible_history(), estimate_email_is_configured(), estimate_csv_response() (+12 more)

### Community 19 - "SourceImportError"
Cohesion: 0.10
Nodes (20): _read(), _aliases_by_normalized_name(), _content_format(), CsvProductFileReader, _header_mapping(), _open_legacy_xls(), ProductFileReader, ProductFileReadResult (+12 more)

### Community 20 - "product_issue_report.py"
Cohesion: 0.12
Nodes (11): build_product_issue_rows(), _cell_text(), _decimal(), export_product_issue_workbook(), _issue_code(), preview_product_issue_workbook(), ProductIssueReportError, _report_values() (+3 more)

### Community 21 - "load_source"
Cohesion: 0.10
Nodes (8): _delete_rows(), load_source(), _purge_old_rows(), rollback_source(), Base, ChannelTests, LoadTests, PrepareTests

### Community 22 - "walk_case"
Cohesion: 0.19
Nodes (11): walk_case(), case(), kti(), kti_case(), line(), PendingNeverZeroTests, sources(), teamex() (+3 more)

### Community 23 - "freight/views.py"
Cohesion: 0.17
Nodes (9): allowed_clients_for(), resolve_authorized_client(), CalculatorAccessServiceTests, api_tools_page(), calculator_page(), freight_accounts(), product_autocomplete(), _render_api_tools() (+1 more)

### Community 24 - "ratecard_compare.py"
Cohesion: 0.09
Nodes (24): _app_amounts(), app_quotes(), app_rate(), attach_translogic(), carrier_configs(), _causes(), _cell(), compare_case() (+16 more)

### Community 25 - "engine"
Cohesion: 0.11
Nodes (16): source_value(), _above_single_band(), check_charges(), _freight_proven(), _kilos(), recalculate(), route_label(), _service_enabled() (+8 more)

### Community 26 - "product_reconciliation.py"
Cohesion: 0.14
Nodes (11): _metres(), resolve_product_dimensions(), build_product_reconciliation(), _decimal(), _different(), _matched_row(), _normalise_text(), _operational_values() (+3 more)

### Community 27 - "import_customers"
Cohesion: 0.10
Nodes (11): CustomerUploadForm, CustomerImportError, CustomerPreview, import_customers(), master_state_digest(), parse_customers_xls(), preview_customers(), Command (+3 more)

### Community 28 - "validate_excel_battery.py"
Cohesion: 0.17
Nodes (15): ActualOutput, Command, _component_decimal(), _decimal(), _display_cubic_from_rating_cubic(), ExpectedOutput, _is_validated(), _money() (+7 more)

### Community 30 - "rate_source_load.py"
Cohesion: 0.12
Nodes (17): _active_version(), _card_fingerprints(), client_carriers(), _integer(), _listed(), _money(), parse_rate_lines(), parse_zone_rows() (+9 more)

### Community 31 - "ChainResolutionTests"
Cohesion: 0.18
Nodes (7): CaseContext, Catalogue, resolve_case(), ChainResolutionTests, line(), rates(), teamex_catalogue()

### Community 32 - "operational_test_runner.py"
Cohesion: 0.12
Nodes (18): Command, _check(), _decimal(), DispatchCase, _finalise_case(), _postcode_map(), _read_dispatch_cases(), _render_markdown() (+10 more)

### Community 33 - "ValidationError"
Cohesion: 0.15
Nodes (9): apply_cubic_margin(), ConsolidatedFreight, build_authorized_freight_request(), _decimal(), validate_consolidated(), validate_location(), ValidationError, CubicMarginTests (+1 more)

### Community 34 - "SavedEstimateTests"
Cohesion: 0.12
Nodes (3): displayed_result(), freight_result(), SavedEstimateTests

### Community 35 - "django_apps"
Cohesion: 0.06
Nodes (10): AuditConfig, AuthenticationGatewayConfig, CarriersConfig, ClientsConfig, FreightConfig, ImportsConfig, LocationsConfig, ProductsConfig (+2 more)

### Community 36 - "generate_acceptance_matrix.py"
Cohesion: 0.13
Nodes (16): _candidate_cases(), _case(), Command, _diagnose_no_quote(), _freight_line(), _product_snapshot(), _render_markdown(), _representative_products() (+8 more)

### Community 37 - "imports/models.py"
Cohesion: 0.05
Nodes (23): _pinned(), _pinned(), _pinned(), Migration, backfill_product_repair_memory(), _fingerprint(), Migration, Migration (+15 more)

### Community 38 - "correction_memory_export.py"
Cohesion: 0.06
Nodes (11): ExternalDataCorrectionMemoryAdmin, ProductReconciliationDecisionAdmin, ProductReconciliationRuleAdmin, ProductSourceRowAdmin, ReadOnlySourceRowAdmin, StockSourceRowAdmin, _build_workbook(), correction_memory_export_response() (+3 more)

### Community 39 - "load_rehearsal"
Cohesion: 0.16
Nodes (6): load_rehearsal(), require_disposable(), _stored(), ValidateError, CommandTests, GuardTests

### Community 40 - "STHUserAdmin"
Cohesion: 0.07
Nodes (6): CalculatorUserProfileAdmin, HiddenCalculatorUserProfileAdmin, STHUserAdmin, configure_user_from_primary_group(), primary_access_group_for(), GroupBasedUserAdminTests

### Community 41 - "operational_ratecards.py"
Cohesion: 0.11
Nodes (14): _sources(), RateCardLine, Meta, ZoneSourceRow, Meta, get_operational_pair(), load_proof(), sources_from_rows() (+6 more)

### Community 42 - "authentication_gateway/views.py"
Cohesion: 0.10
Nodes (3): CalculatorLoginView, csrf_failure(), permission_denied_view()

### Community 43 - "ftp_automation.py"
Cohesion: 0.11
Nodes (11): FtpInboxAdminMixin, FtpSourceWaiting, next_configuration_check(), process_ftp_configuration(), _read_configured_source(), _save_result(), _create_snapshot(), _existing_snapshot() (+3 more)

### Community 44 - "create_audit_event"
Cohesion: 0.10
Nodes (26): ExternalDataCorrectionMemory, Meta, create_audit_event(), canonical_fingerprint(), CorrectionMemoryMatch, find_correction_memory(), mark_correction_memories_used(), remember_correction() (+18 more)

### Community 45 - "classify"
Cohesion: 0.40
Nodes (6): classify(), app(), ClassificationTests, config(), engine(), rate()

### Community 46 - "ProductMaster"
Cohesion: 0.06
Nodes (7): safe_filename(), ProductMaster, Meta, ContinuityStateTests, UnknownDimensionProductNoticeTests, ProductMasterOperationalStatusTests, ProductMasterReadOnlyBridgeTests

### Community 47 - "Command"
Cohesion: 0.18
Nodes (4): Command, d(), s(), yes()

### Community 49 - "pdf_export.py"
Cohesion: 0.15
Nodes (14): _body_table_style(), estimate_pdf_bytes(), _grid_table_style(), _header_table(), _items_table(), _money(), _options_table(), _shipment_table() (+6 more)

### Community 50 - "StockMasterAdmin"
Cohesion: 0.11
Nodes (4): GlobalReconciliationFilterForm, StockMasterAdmin, StockMasterDetailsFilterForm, StockMasterUploadForm

### Community 52 - "destinations"
Cohesion: 0.21
Nodes (5): destinations(), shapes(), DestinationTests, IsolationTests, ShapeTests

### Community 54 - "ExternalDataFileAdmin"
Cohesion: 0.12
Nodes (3): ExternalDataFileAdmin, FuelActivationForm, FuelRollbackForm

### Community 55 - "postcodes_apply.py"
Cohesion: 0.21
Nodes (19): _actor_name(), _append_batch(), _batch_actor(), _build_item_plan(), build_postcodes_rollback_plan(), _created_record_for_source(), _exact_rows(), _final_for_item() (+11 more)

### Community 56 - "is_django_administrator"
Cohesion: 0.06
Nodes (7): is_django_administrator(), ClientAdmin, CommercialCustomerAdmin, CustomerAdmin, CustomerImportAdmin, CustomerSectionAdmin, FreightCalculatorAdmin

### Community 57 - "CalculatorCustomerEnableTests"
Cohesion: 0.12
Nodes (5): EnableCalculatorCustomerForm, CalculatorCustomerConflict, enable_calculator_customer(), _enable_calculator_customer(), CalculatorCustomerEnableTests

### Community 58 - "overlength_fee"
Cohesion: 0.14
Nodes (4): overlength_fee(), OverlengthNotConfigured, BandTests, seed()

### Community 59 - "apply_approved_postcodes"
Cohesion: 0.19
Nodes (8): apply_approved_postcodes(), _apply_audit_metadata(), ensure_postcodes_apply_audit_event(), _find_apply_audit_event(), _latest_open_batch(), postcodes_review_completion(), PostcodesApplyBlocked, PostcodesReviewAuditCompletionTests

### Community 60 - "emailing.py"
Cohesion: 0.18
Nodes (9): EstimateEmailError, is_customer_user(), recipient_options_for_client(), RecipientOption, resolve_recipient(), send_estimates_email(), _subject_for(), _valid_email() (+1 more)

### Community 61 - "xlsx_reader.py"
Cohesion: 0.12
Nodes (21): StockSourceRow, Meta, build_product_source_validation_report(), _comparison_details(), _comparison_summary(), _dimension_status(), _is_empty_placeholder(), _parse_product_records() (+13 more)

### Community 62 - "validate_sth_rate_sources.py"
Cohesion: 0.17
Nodes (5): Command, _validate_carrier(), priced_zones(), _decode(), summarise_carrier()

### Community 63 - ".handle"
Cohesion: 0.15
Nodes (6): Command, Command, render_markdown(), carrier_configs_or_fail(), counts(), rate_rows()

### Community 65 - "RatecardUploadAdminMixin"
Cohesion: 0.12
Nodes (5): RatecardUploadAdminMixin, RatecardUploadForm, RateSourceRollbackForm, ZoneUploadForm, safe_csv_cell()

### Community 66 - "scan_ftp_inbox"
Cohesion: 0.24
Nodes (6): _display_local_timestamp(), ftp_file_map(), inspect_ftp_inbox(), _latest_snapshot(), scan_ftp_inbox(), FtpInboxTests

### Community 67 - "ratecard_walk.py"
Cohesion: 0.14
Nodes (15): _quoted(), _amount(), _apply_fuel(), _between(), _evaluate(), _is_freight(), _is_zone_line(), _money() (+7 more)

### Community 69 - "ExternalDataReviewItemInline"
Cohesion: 0.14
Nodes (3): ExternalDataReviewItemInline, Media, PostcodesReviewPhase2ATests

### Community 71 - "ProductCorrectionBulkUiTests"
Cohesion: 0.08
Nodes (7): preview_changed_values(), ProductReconciliationWorkflow, reconciliation_progress(), rows_for_review_status(), ProductReconciliationBulkForm, ProductReconciliationIndividualForm, ProductCorrectionBulkUiTests

### Community 74 - "ProductFileAdapterTests"
Cohesion: 0.17
Nodes (3): FakeSheet, FakeWorkbook, ProductFileAdapterTests

### Community 76 - "load_cases"
Cohesion: 0.19
Nodes (7): _case_from_row(), freight_lines(), load_cases(), with_ids(), with_totals(), ConsignmentTests, products()

### Community 78 - "test_ratecard_walk.py"
Cohesion: 0.18
Nodes (6): Line, CochranesRootTests, FuelSourceTests, IsolationTests, ScopeTests, SteadfastTests

### Community 80 - "FreightCalculator"
Cohesion: 0.14
Nodes (4): FreightCalculator, Meta, ClientAdminVisibilityTests, FreightCalculatorOptionsTests

### Community 82 - "FtpImportConfiguration"
Cohesion: 0.18
Nodes (4): FtpImportConfiguration, Meta, process_due_ftp_configurations(), FtpImportAutomationTests

### Community 83 - "Customer"
Cohesion: 0.15
Nodes (4): CommercialCustomerAdminForm, CommercialCustomerCodeSearch, Customer, Meta

### Community 84 - "ratecard_chain.py"
Cohesion: 0.24
Nodes (8): _between(), CaseResult, _evaluate(), expression_issue(), _is_freight(), _record_terminal(), _reference(), _walk()

### Community 85 - "test_ratecard_chain.py"
Cohesion: 0.20
Nodes (6): validate_sources(), CardLine, load_catalogue(), _number(), LoadCatalogueTests, RealSourceTests

### Community 88 - "clients/admin.py"
Cohesion: 0.12
Nodes (5): CommercialCustomerCodeWidget, CustomerLinksToRemoveField, FreightCalculatorAdminForm, Meta, LinkedFilter

### Community 90 - "CustomerSection"
Cohesion: 0.11
Nodes (6): CommercialCustomer, Meta, CustomerSection, Meta, CommercialCustomerAdminTests, CustomerSectionsTests

### Community 91 - "sync_postcodes_review_items"
Cohesion: 0.12
Nodes (6): build_postcodes_apply_plan(), build_postcodes_review_row_key(), sync_postcodes_review_items(), ExternalDataReviewTests, PostcodesApplyApprovedTests, PostcodesHistoricalComparisonCompactTests

### Community 92 - "CompareError"
Cohesion: 0.20
Nodes (5): Command, CompareError, _decimal_or_none(), read_translogic(), TransLogicTests

### Community 93 - "SavedEstimate"
Cohesion: 0.15
Nodes (5): SavedEstimateAdmin, current_validity_end(), current_validity_start(), SavedEstimate, Meta

### Community 96 - "ratecard_operational.py"
Cohesion: 0.17
Nodes (5): Command, activate_operational_pair(), build_operational_gate(), OperationalGateTests, valid_report()

### Community 103 - "estimate_actions.js"
Cohesion: 0.42
Nodes (8): applyCalculationPayload(), loadDuplicate(), loadSavedEstimateCount(), markUnsaved(), readJsonResponse(), saveCurrentEstimate(), setStatus(), updatePrintAvailability()

### Community 105 - "FreightRequest"
Cohesion: 0.20
Nodes (4): FreightRequest, QuoteTests, QuotedWeightBandTests, calculate()

### Community 106 - "FtpImportSchedule"
Cohesion: 0.22
Nodes (4): FtpImportScheduleForm, Meta, FtpImportSchedule, Meta

### Community 108 - "ratecard_coverage.py"
Cohesion: 0.23
Nodes (5): _csv_row(), Summary, sweep(), in_scope(), route_rows()

### Community 110 - "CalculatorUserProfile"
Cohesion: 0.09
Nodes (8): CalculatorRoleFilter, CalculatorScopeFilter, Command, CalculatorUserProfile, ClientScope, Meta, Role, DjangoAdminAccessMiddlewareTests

### Community 112 - "StockMaster"
Cohesion: 0.27
Nodes (3): Command, StockMaster, Meta

### Community 120 - "carriers/admin.py"
Cohesion: 0.15
Nodes (4): CarrierServiceAdmin, CarrierServiceInline, ClientCarrierConfigAdmin, ClientCarrierConfigInline

### Community 122 - "estimate_email.js"
Cohesion: 0.80
Nodes (4): populateRecipients(), selectedClient(), selectedSelectors(), updateState()

### Community 123 - "FakeSheet"
Cohesion: 0.33
Nodes (3): fake_book(), FakeSheet, source_rows()

### Community 124 - "Case"
Cohesion: 0.18
Nodes (4): _case_fields(), Command, Case, walk_all()

### Community 127 - "check_zones"
Cohesion: 0.24
Nodes (3): check_zones(), IsolationTests, SourceGuardTests

### Community 165 - "persist_exception_evidence"
Cohesion: 0.38
Nodes (3): persist_exception_evidence(), ExceptionIngestionTests, source()

### Community 166 - "_teamex_weight_break"
Cohesion: 0.28
Nodes (3): _teamex_weight_break(), _tfmx_weight_break(), WeightBandTests

### Community 167 - "ImportReconciliationException"
Cohesion: 0.22
Nodes (3): ImportReconciliationException, Meta, ImportExceptionRegistryTests

### Community 169 - "ProductKitComponent"
Cohesion: 0.29
Nodes (3): ProductKitComponent, Meta, ProductAdminVisibilityTests

### Community 179 - "_best_alias_candidate"
Cohesion: 0.50
Nodes (3): _best_alias_candidate(), _compact_suburb_name(), _new_row_diagnostics()

## Knowledge Gaps
- **97 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Client` connect `Client` to `Product`, `calculator.py`, `admin_reconciliation.py`, `FTPPostcodesImportTests`, `fuel.py`, `snapshots.py`, `FuelXlsFlowTests`, `GlobalStockMasterTests`, `imports/admin.py`, `ProductReconciliationWorkspaceTests`, `global_stock_master.py`, `clients/models.py`, `PostcodesReviewItemForm`, `authentication_gateway/admin.py`, `ExternalDataFile`, `product_issue_report.py`, `load_source`, `freight/views.py`, `ratecard_compare.py`, `product_reconciliation.py`, `import_customers`, `validate_excel_battery.py`, `ProductStockSourceTests`, `operational_test_runner.py`, `SavedEstimateTests`, `generate_acceptance_matrix.py`, `imports/models.py`, `persist_exception_evidence`, `load_rehearsal`, `STHUserAdmin`, `ProductKitComponent`, `AccessManagementCommandTests`, `ftp_automation.py`, `Command`, `create_audit_event`, `AcceptanceMatrixCommandTests`, `Command`, `ProductMaster`, `ProductMasterReadOnlyReconciliation`, `FreightUserAccessTests`, `ExternalDataFileAdmin`, `CalculatorCustomerEnableTests`, `overlength_fee`, `apply_approved_postcodes`, `xlsx_reader.py`, `FtpImportScheduleAdmin`, `scan_ftp_inbox`, `ExternalDataReviewItemInline`, `FtpImportScheduleAdminTests`, `ProductCorrectionBulkUiTests`, `RatecardUploadTests`, `FtpImportConfigurationAdmin`, `FreightCalculator`, `validate_product_master`, `FtpImportConfiguration`, `ProductClientIdentityTests`, `clients/admin.py`, `CustomerSection`, `sync_postcodes_review_items`, `CalculatorLoginSecurityTests`, `CalculatorVisualContractTests`, `ratecard_operational.py`, `CalculatorLoginFlowTests`, `CommandTests`, `SweepTests`, `FreightRequest`, `CalculatorUserProfile`, `Command`, `ExceptionAdminImportTests`, `ProductAdmin`?**
  _High betweenness centrality (0.240) - this node is a cross-community bridge._
- **Are the 102 inferred relationships involving `Client` (e.g. with `_calculator_client_field()` and `PrimaryAccessFieldsMixin`) actually correct?**
  _`Client` has 102 INFERRED edges - model-reasoned connections that need verification._
- **Should `Product` be split into smaller, more focused modules?**
  _Cohesion score 0.0711864406779661 - nodes in this community are weakly interconnected._
- **Why does `ExternalDataFile` connect `ExternalDataFile` to `Product`, `calculator.py`, `admin_reconciliation.py`, `FTPPostcodesImportTests`, `fuel.py`, `Client`, `FuelXlsFlowTests`, `GlobalStockMasterTests`, `imports/admin.py`, `ProductReconciliationWorkspaceTests`, `clients/models.py`, `PostcodesReviewItemForm`, `product_issue_report.py`, `load_source`, `product_reconciliation.py`, `ProductStockSourceTests`, `rate_source_load.py`, `imports/models.py`, `load_rehearsal`, `operational_ratecards.py`, `ftp_automation.py`, `create_audit_event`, `ProductMaster`, `Command`, `ProductMasterReadOnlyReconciliation`, `ExternalDataFileAdmin`, `postcodes_apply.py`, `apply_approved_postcodes`, `xlsx_reader.py`, `FtpImportScheduleAdmin`, `RatecardUploadAdminMixin`, `scan_ftp_inbox`, `ProductRejectedRowsBulkReview`, `ExternalDataReviewItemInline`, `FtpImportScheduleAdminTests`, `ProductCorrectionBulkUiTests`, `RatecardUploadTests`, `validate_product_master`, `FtpImportConfiguration`, `ProductClientIdentityTests`, `sync_postcodes_review_items`, `ratecard_operational.py`, `PostcodesAdminPresentationTests`, `Command`?**
  _High betweenness centrality (0.129) - this node is a cross-community bridge._
- **Are the 94 inferred relationships involving `ExternalDataFile` (e.g. with `FreightCalculatorService` and `OperationalRateEngine`) actually correct?**
  _`ExternalDataFile` has 94 INFERRED edges - model-reasoned connections that need verification._
- **Should `calculator.py` be split into smaller, more focused modules?**
  _Cohesion score 0.0792156862745098 - nodes in this community are weakly interconnected._
- **Why does `SavedEstimateTests` connect `SavedEstimateTests` to `Product`, `Client`, `CalculatorUserProfile`, `clients/models.py`, `FreightCalculator`, `SavedEstimate`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._