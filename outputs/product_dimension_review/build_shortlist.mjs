import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "C:/Docker-Projects/Calc-v1.8";
const outputDir = `${root}/outputs/product_dimension_review`;
const payload = JSON.parse(await fs.readFile(
  `${root}/reports/product_dimension_review/shortlist_data.json`, "utf8"
));

const wb = Workbook.create();
const ws = wb.worksheets.add("Dimension review");
ws.showGridLines = false;
ws.tabColor = "#1F4E78";

const headers = [
  "SKU", "Approval decision", "Approval notes",
  "Approved length (m)", "Approved width (m)", "Approved height (m)",
  "Product Master row", "Name", "Description", "Category",
  "Current length (m)", "Current width (m)", "Current height (m)",
  "Current weight (kg)", "Current cubic (m³)", "Quantity", "Pallet", "Status", "Current comment",
  "Historical SKUs row", "Historical length (m)", "Historical width (m)", "Historical height (m)",
  "Historical weight (kg)", "Historical cubic (m³)", "Historical type",
  "Combo flag", "M3ERROR flag", "KGERROR flag", "Historical FIX",
  "Weight difference (kg)", "Cubic difference (m³)", "Blocking reason"
];

const rows = payload.rows.map((r) => [
  r.sku, r.approval_decision, r.approval_notes,
  r.approved_length_m, r.approved_width_m, r.approved_height_m,
  r.current_row, r.name, r.description, r.category,
  r.current_length_m, r.current_width_m, r.current_height_m,
  r.current_weight_kg, r.current_cubic_m3, r.current_quantity, r.current_pallet,
  r.current_status, r.current_comment,
  r.historical_row, r.historical_length_m, r.historical_width_m, r.historical_height_m,
  r.historical_weight_kg, r.historical_cubic_m3, r.historical_type,
  r.combo_flag, r.m3error_flag, r.kgerror_flag, r.historical_fix,
  r.weight_difference_kg, r.cubic_difference_m3, r.blocking_reason
]);

ws.getRange("A2").values = [["Blocked product dimension review"]];
ws.getRange("A2").format.font = { name: "Arial", size: 15, bold: true, color: "#1F1F1F" };
ws.getRange("A3:AG3").format.borders = { bottom: { style: "thin", color: "#1F4E78" } };
ws.getRange("A5:B8").values = [
  ["Blocked Product Master rows", payload.controls.blocked_current_rows],
  ["With positive historical dimensions", payload.controls.blocked_with_positive_historical_dimensions],
  ["Shortlisted for review", payload.controls.shortlist_rows],
  ["Approval decisions still pending", null],
];
ws.getRange("B8").formulas = [[`=COUNTIF(B11:B${10 + rows.length},"Pending")`]];
ws.getRange("D5:E8").values = [
  ["Weight match tolerance (kg)", payload.controls.weight_tolerance_kg],
  ["Cubic match tolerance (m³)", payload.controls.cubic_tolerance_m3],
  ["Database changes", "None"],
  ["Required next action", "Business owner dimension approval"],
];
ws.getRange("G5:H8").values = [
  ["Current source", payload.sources.current],
  ["Current SHA-256", payload.sources.current_sha256],
  ["Historical source", payload.sources.historical],
  ["Historical SHA-256", payload.sources.historical_sha256],
];
ws.getRange("A5:H8").format.font = { name: "Arial", size: 10 };
ws.getRange("A5:A8").format.font.bold = true;
ws.getRange("D5:D8").format.font.bold = true;
ws.getRange("G5:G8").format.font.bold = true;
ws.getRange("B5:B8").format.fill = "#D9EAF7";
ws.getRange("E5:E8").format.fill = "#E2F0D9";
ws.getRange("H5:H8").format.fill = "#F2F2F2";
ws.getRange("A5:A8").format.wrapText = true;
ws.getRange("D5:D8").format.wrapText = true;
ws.getRange("G5:G8").format.wrapText = true;
ws.getRange("H5:H8").format.wrapText = true;

ws.getRange("A10").write([headers, ...rows]);
const endRow = 10 + rows.length;
const table = ws.tables.add(`A10:AG${endRow}`, true, "DimensionReviewTable");
table.style = "TableStyleMedium2";
table.showBandedColumns = false;
table.showFilterButton = true;

ws.getRange(`A10:AG${endRow}`).format.font = { name: "Arial", size: 10, color: "#1F1F1F" };
ws.getRange("A10:AG10").format = {
  fill: "#1F4E78",
  font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { insideVertical: { style: "thin", color: "#FFFFFF" } },
};
ws.getRange(`B11:F${endRow}`).format.fill = "#FFF2CC";
ws.getRange(`B11:B${endRow}`).dataValidation = {
  rule: { type: "list", values: ["Pending", "Approved", "Rejected", "Needs clarification"] }
};
ws.getRange(`B11:B${endRow}`).conditionalFormats.add("containsText", {
  text: "Pending", format: { fill: "#FFF2CC", font: { color: "#7F6000", bold: true } }
});
ws.getRange(`B11:B${endRow}`).conditionalFormats.add("containsText", {
  text: "Approved", format: { fill: "#E2F0D9", font: { color: "#375623", bold: true } }
});
ws.getRange(`B11:B${endRow}`).conditionalFormats.add("containsText", {
  text: "Rejected", format: { fill: "#FCE4D6", font: { color: "#9C0006", bold: true } }
});

for (const range of ["D11:F62", "K11:Q62", "U11:Y62", "AE11:AF62"]) {
  ws.getRange(range).format.numberFormat = "0.000";
}
ws.getRange(`G11:G${endRow}`).format.numberFormat = "0";
ws.getRange(`T11:T${endRow}`).format.numberFormat = "0";
ws.getRange(`A11:A${endRow}`).format.numberFormat = "@";
ws.getRange(`A11:AG${endRow}`).format.verticalAlignment = "top";
ws.getRange(`A11:AG${endRow}`).format.wrapText = false;

const widths = {
  A: 22, B: 20, C: 28, D: 22, E: 15, F: 15, G: 20, H: 38, I: 34, J: 12,
  K: 14, L: 14, M: 14, N: 16, O: 16, P: 10, Q: 9, R: 9, S: 32,
  T: 16, U: 17, V: 17, W: 17, X: 18, Y: 18, Z: 14,
  AA: 12, AB: 14, AC: 14, AD: 16, AE: 18, AF: 18, AG: 38,
};
for (const [column, width] of Object.entries(widths)) {
  ws.getRange(`${column}:${column}`).format.columnWidth = width;
}
ws.getRange("1:1").format.rowHeight = 12;
ws.getRange("2:2").format.rowHeight = 24;
ws.getRange("5:8").format.rowHeight = 34;
ws.getRange("10:10").format.rowHeight = 36;
ws.freezePanes.freezeRows(10);
ws.freezePanes.freezeColumns(2);

wb.recalculate();
const inspection = await wb.inspect({
  kind: "table",
  range: `Dimension review!A2:H12`,
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 8,
  maxChars: 8000,
});
await fs.writeFile(`${outputDir}/inspection.ndjson`, inspection.ndjson, "utf8");
const errors = await wb.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
await fs.writeFile(`${outputDir}/formula_errors.ndjson`, errors.ndjson, "utf8");
const preview = await wb.render({ sheetName: "Dimension review", range: "A1:H18", scale: 1.2, format: "png" });
await fs.writeFile(`${outputDir}/preview.png`, new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(`${outputDir}/blocked_product_dimension_review_20261119.xlsx`);
console.log(JSON.stringify({ rows: rows.length, endRow, output: `${outputDir}/blocked_product_dimension_review_20261119.xlsx` }));
