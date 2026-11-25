from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    KeepTogether,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "pdf" / "operational_freight_quote_validation_pack.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

NAVY = colors.HexColor("#16324F")
BLUE = colors.HexColor("#2878A8")
PALE = colors.HexColor("#EAF3F8")
GREEN = colors.HexColor("#E8F4EA")
AMBER = colors.HexColor("#FFF3D6")
RED = colors.HexColor("#FBE9E7")
GREY = colors.HexColor("#F2F4F5")
MID = colors.HexColor("#657580")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="Title2", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=20,
                          leading=24, textColor=NAVY, alignment=TA_CENTER, spaceAfter=8))
styles.add(ParagraphStyle(name="Sub", parent=styles["Normal"], fontSize=9, leading=12,
                          textColor=MID, alignment=TA_CENTER, spaceAfter=12))
styles.add(ParagraphStyle(name="H1x", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=14,
                          leading=17, textColor=NAVY, spaceBefore=4, spaceAfter=7))
styles.add(ParagraphStyle(name="H2x", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10.5,
                          leading=13, textColor=BLUE, spaceBefore=6, spaceAfter=4))
styles.add(ParagraphStyle(name="Bodyx", parent=styles["BodyText"], fontSize=8.7, leading=12, spaceAfter=4))
styles.add(ParagraphStyle(name="Smallx", parent=styles["BodyText"], fontSize=7.6, leading=10))
styles.add(ParagraphStyle(name="Tiny", parent=styles["BodyText"], fontSize=6.8, leading=8.5))
styles.add(ParagraphStyle(name="Callout", parent=styles["BodyText"], fontSize=9, leading=12,
                          borderColor=BLUE, borderWidth=0.8, borderPadding=7, backColor=PALE, spaceAfter=8))


def P(text, style="Bodyx"):
    return Paragraph(text, styles[style])


def checkbox(label):
    return P(f"[ ] {label}", "Smallx")


def ruled_rows(labels, widths=(48*mm, 127*mm), height=8*mm):
    data = [[P(label, "Smallx"), ""] for label in labels]
    t = Table(data, colWidths=list(widths), rowHeights=[height] * len(data))
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AEB8BE")),
        ("BACKGROUND", (0, 0), (0, -1), GREY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def standard_table(data, widths, header=True, font=7.3, row_bgs=None):
    converted = []
    for row in data:
        converted.append([cell if hasattr(cell, "wrap") else P(str(cell), "Smallx") for cell in row])
    t = Table(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AEB8BE")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        commands += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    if row_bgs:
        for row, colour in row_bgs.items():
            commands.append(("BACKGROUND", (0, row), (-1, row), colour))
    t.setStyle(TableStyle(commands))
    return t


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#CAD2D7"))
    canvas.line(18*mm, 15*mm, 192*mm, 15*mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MID)
    canvas.drawString(18*mm, 10*mm, "STH Operational Freight Quote Validation Pack")
    canvas.drawRightString(192*mm, 10*mm, f"Page {doc.page}")
    canvas.restoreState()


story = []

# Page 1 - rules
story += [
    P("Operational Freight Quote Validation Pack", "Title2"),
    P("Printable business-rule checklist | Australia | Version 1.0 | 20 November 2026", "Sub"),
    P("Purpose", "H1x"),
    P("Use this pack to confirm that the application follows the correct operational procedure. A different dollar value from the historical workbook is not automatically an error because rates can change. The current approved Rates and Zones files are the pricing authority; the workbook is comparison evidence only.", "Callout"),
    P("1. Required source hierarchy", "H1x"),
    standard_table([
        ["Priority", "Source", "Business rule"],
        ["1", "Current operational master data", "Products, suburbs/postcodes, fuel and stock must come from the activated central operational data."],
        ["2", "Current Rates and Zones imports", "Carrier zone, rate-card path, weight break and confirmed source charges must come from the active imported files."],
        ["3", "Approved configuration", "Cubic conversion, pallet tare, overlength, uprate, tailgate and other configured rules apply only when enabled."],
        ["4", "Historical workbook", "Use to compare procedure and investigate differences. Do not override current operational data merely to reproduce an old price."],
    ], [15*mm, 50*mm, 110*mm]),
    Spacer(1, 5*mm),
    P("2. Calculation sequence", "H1x"),
    standard_table([
        ["Step", "Rule", "Manual check"],
        ["A", "Validate the request", "Origin, destination, postcode, SKU, quantity and requested services are present."],
        ["B", "Resolve product data", "Use active client product dimensions, unit weight, freight type and quantity. Reject or warn on missing/non-positive operational dimensions."],
        ["C", "Consolidate the load", "Sum product volume and weight; add applicable pallet/tare values; retain maximum item length for overlength."],
        ["D", "Calculate chargeable weight", "For each carrier: MAX(actual weight, rating cubic metres x carrier cubic conversion). Apply the configured rounding/band rule."],
        ["E", "Resolve destination zone", "Match the destination using the operational Zones file and the zone type required by that carrier/rate-card path."],
        ["F", "Walk the rate-card chain", "Follow the carrier root card through references. Select the applicable zone, freight type and weight break."],
        ["G", "Calculate confirmed charges", "Apply base/minimum, weight charge, fuel and confirmed surcharges according to the active source expressions."],
        ["H", "Apply configured extras", "Add overlength, uprate, tailgate, handling, remote/offshore or other enabled application charges in their defined order."],
        ["I", "Classify the result", "COMPLETE, PROVISIONAL or NO QUOTE using the decision rules on page 3."],
        ["J", "Round and display", "Round only at the configured display/final stage. Keep the unrounded audit values."],
    ], [12*mm, 48*mm, 115*mm]),
]

story.append(PageBreak())

# Page 2 - blank case worksheet
story += [
    P("Quote Case Worksheet", "Title2"),
    P("Complete one sheet per test case. Attach screenshots and source extracts where required.", "Sub"),
    P("A. Test identification", "H1x"),
    ruled_rows(["Test ID", "Tester", "Date / time (Australia/Adelaide)", "Application version / branch", "Rates file and activation", "Zones file and activation"]),
    Spacer(1, 4*mm),
    P("B. Request and consolidated load", "H1x"),
    ruled_rows(["Client", "Origin suburb / state / postcode", "Destination suburb / state / postcode", "SKU(s) and quantities", "Tailgate / other services", "Product volume and weight", "Pallet/tare additions", "Final rating cubic metres", "Final actual weight", "Maximum item length"]),
    Spacer(1, 4*mm),
    P("C. Input controls", "H1x"),
    standard_table([
        ["Check", "Pass", "Fail", "Evidence / comment"],
        ["SKU exists in active operational products", "[ ]", "[ ]", ""],
        ["Dimensions and weight are valid positive values", "[ ]", "[ ]", ""],
        ["Destination resolves to the intended suburb/postcode", "[ ]", "[ ]", ""],
        ["No unapproved fallback to development workbook data", "[ ]", "[ ]", ""],
        ["Requested optional services are represented correctly", "[ ]", "[ ]", ""],
    ], [75*mm, 15*mm, 15*mm, 70*mm]),
    Spacer(1, 5*mm),
    P("D. Overall acceptance", "H1x"),
    standard_table([
        ["Decision", "Select", "Rule"],
        ["PASS", "[ ]", "All mandatory procedural checks pass; every displayed amount is reproducible from active sources."],
        ["PASS WITH WARNING", "[ ]", "A provisional estimate is correctly labelled and every excluded unresolved charge is visible."],
        ["FAIL", "[ ]", "Incorrect input, zone, weight, rate path, charge, classification, hidden fallback or unexplained amount."],
    ], [42*mm, 18*mm, 115*mm], row_bgs={1: GREEN, 2: AMBER, 3: RED}),
    Spacer(1, 4*mm),
    ruled_rows(["Tester conclusion", "Required follow-up", "Reviewer / approval", "Approval date"]),
]

story.append(PageBreak())

# Page 3 - per carrier and decision rules
story += [
    P("Carrier Calculation and Decision Rules", "Title2"),
    P("Repeat the carrier table for every service returned or rejected by the application.", "Sub"),
    P("A. Per-carrier calculation", "H1x"),
    standard_table([
        ["Field", "Expected / manual result", "Application result", "Pass"],
        ["Carrier and service", "", "", "[ ]"],
        ["Resolved zone and zone type", "", "", "[ ]"],
        ["Actual weight", "", "", "[ ]"],
        ["Volumetric weight", "rating m3 x conversion =", "", "[ ]"],
        ["Chargeable weight / band", "MAX(actual, volumetric) =", "", "[ ]"],
        ["Rate-card path", "", "", "[ ]"],
        ["Base/minimum/weight charge", "", "", "[ ]"],
        ["Fuel charge", "", "", "[ ]"],
        ["Confirmed source surcharges", "", "", "[ ]"],
        ["Configured application extras", "", "", "[ ]"],
        ["Excluded unresolved charges", "", "", "[ ]"],
        ["Unrounded total", "", "", "[ ]"],
        ["Displayed total", "", "", "[ ]"],
        ["Result classification", "COMPLETE / PROVISIONAL / NO QUOTE", "", "[ ]"],
    ], [48*mm, 55*mm, 55*mm, 17*mm]),
    Spacer(1, 5*mm),
    P("B. Mandatory result classification", "H1x"),
    standard_table([
        ["Result", "When it is allowed", "What must be displayed"],
        ["COMPLETE", "A zone and applicable rate are found; the entire required rate-card chain and all applicable charges are resolved.", "Final amount. No unresolved-charge warning."],
        ["PROVISIONAL", "A usable confirmed subtotal exists, but one or more source charges cannot be resolved safely.", "Confirmed-charge amount only; prominent provisional label; each excluded charge and reason; Customer Service direction."],
        ["NO QUOTE", "No destination zone, no applicable base rate, or no usable confirmed subtotal exists.", "No monetary quote; precise reason such as NO_ZONE or NO_RATE; Customer Service direction."],
    ], [32*mm, 77*mm, 66*mm], row_bgs={1: GREEN, 2: AMBER, 3: RED}),
    Spacer(1, 5*mm),
    P("C. Non-negotiable controls", "H1x"),
    standard_table([
        ["Control", "Pass condition"],
        ["No invented charge", "An unresolved charge must never be guessed or silently included."],
        ["No hidden omission", "Every applicable but excluded charge must be named with its reason."],
        ["No false final price", "A subtotal with unresolved charges must never be labelled final or complete."],
        ["No unusable partial", "If no reliable confirmed subtotal exists, return NO QUOTE rather than zero or a misleading estimate."],
        ["Traceability", "The result records active source versions, zone, weights, rate-card path, charge components and warnings."],
        ["Customer direction", "Unresolved operational cases direct the user to Steadfast Customer Service."],
    ], [48*mm, 127*mm]),
]

story.append(PageBreak())

# Page 4 - numeric calculation audit
story += [
    P("Numeric Calculation Audit", "Title2"),
    P("Independent hand calculation and historical workbook comparison for the worked example", "Sub"),
    P("1. Common load calculation", "H1x"),
    standard_table([
        ["Calculation", "Formula", "Result", "Check"],
        ["Product cubic", "Operational stored cubic for 3DALIGNER-FP", "2.687 m3", "[ ]"],
        ["Rating cubic", "2.687 + 0.020 pallet allowance", "2.707 m3", "[ ]"],
        ["Actual weight", "268.000 + 32.500 pallet tare", "300.500 kg", "[ ]"],
        ["TEAMEX volumetric", "2.707 x 334 kg/m3", "904.138 kg", "[ ]"],
        ["TEAMEX chargeable", "MAX(300.500, 904.138), rounded to band kg", "905 kg", "[ ]"],
        ["TFMX volumetric", "2.707 x 250 kg/m3", "676.750 kg", "[ ]"],
        ["TFMX chargeable", "MAX(300.500, 676.750), rounded to band kg", "677 kg", "[ ]"],
    ], [43*mm, 78*mm, 38*mm, 16*mm]),
    Spacer(1, 4*mm),
    P("2. Current operational TEAMEX ROAD", "H1x"),
    standard_table([
        ["Component", "Source / formula", "Amount"],
        ["Freight", "Card 1518, row 3880: MAX($114.80 minimum, $26.88 basic + $0.322 x 905 kg)", "$318.290000"],
        ["Fuel", "Card 1115, row 2: $318.29 x 44%", "$140.047600"],
        ["Confirmed catalogue subtotal", "$318.290000 + $140.047600", "$458.337600"],
        ["Overlength", "Configured charge for 2.900 m", "$60.000000"],
        ["Uprate / handling", "0% / $0", "$0.000000"],
        ["Unrounded estimate", "$458.337600 + $60.000000", "$518.337600"],
        ["Displayed estimate", "Round up to the next cent", "$518.34"],
        ["Excluded", "Disaster Levy S/Chg - zone type absent from zones.csv", "Not included"],
    ], [39*mm, 106*mm, 30*mm], row_bgs={7: GREEN, 8: AMBER}),
    Spacer(1, 4*mm),
    P("3. Current operational TFMX ROAD", "H1x"),
    standard_table([
        ["Component", "Source / formula", "Amount"],
        ["Freight", "Card 1412, row 277: MAX($15.92 minimum, $14.07 basic + $0.883 x 677 kg)", "$611.861000"],
        ["Fuel", "Card 689, row 8354: $611.861 x 51%", "$312.049110"],
        ["Confirmed catalogue subtotal", "$611.861000 + $312.049110", "$923.910110"],
        ["Overlength / uprate / handling", "$0 / 0% / $0", "$0.000000"],
        ["Displayed estimate", "Round up to the next cent", "$923.92"],
        ["Excluded", "Force Majure Charge - price limit unconfirmed", "Not included"],
        ["Excluded", "Disaster Levy S/Chg - target card 1594 missing", "Not included"],
    ], [39*mm, 106*mm, 30*mm], row_bgs={5: GREEN, 6: AMBER, 7: AMBER}),
]

story.append(PageBreak())

# Page 5 - workbook calculation and filled current example
story += [
    P("Workbook Calculation and Worked Result", "Title2"),
    P("Woodville North SA 5012 to ACTON ACT 2601 | 3DALIGNER-FP x 1 | No tailgate", "Sub"),
    P("1. Historical workbook TEAMEX ROAD - hand calculation", "H1x"),
    standard_table([
        ["Component", "Workbook formula / value", "Amount"],
        ["Freight", "MAX($114.80 minimum, $26.88 basic + $0.322 x 905 kg)", "$318.290000"],
        ["Fuel", "$318.29 x historical workbook fuel rate 24%", "$76.389600"],
        ["Overlength", "Historical workbook overlength for 2.900 m", "$60.000000"],
        ["Workbook unrounded total", "$318.290000 + $76.389600 + $60.000000", "$454.679600"],
        ["Workbook displayed total", "Displayed to 2 decimals", "$454.68"],
    ], [42*mm, 103*mm, 30*mm], row_bgs={5: GREEN}),
    Spacer(1, 3*mm),
    P("The $63.658 difference before display rounding is explained by fuel: the current operational source applies 44% ($140.0476), while the historical workbook used 24% ($76.3896). Freight and overlength are identical. Therefore the current amount can be correct even though it does not equal the workbook.", "Callout"),
    P("2. Consolidated inputs", "H1x"),
    standard_table([
        ["Item", "Value", "Validation"],
        ["Product dimensions", "2.900 m x 1.130 m x 0.820 m", "Operational product record"],
        ["Product weight / cubic", "268.000 kg / 2.687 m3", "Operational product record"],
        ["Pallet/tare effect", "+32.500 kg / +0.020 m3", "300.500 kg / 2.707 m3 final rating load"],
        ["Destination", "ACTON ACT 2601", "Valid destination"],
        ["Maximum length", "2.900 m", "Used for overlength assessment"],
    ], [48*mm, 63*mm, 64*mm]),
    Spacer(1, 4*mm),
    P("3. Operational results to validate", "H1x"),
    standard_table([
        ["Service", "Core procedure", "Current outcome", "Paper decision"],
        ["TEAMEX ROAD", "Zone CANB; 905 kg chargeable; $60 overlength", "$518.34 PROVISIONAL. Disaster Levy excluded: ZONE_TYPE_NOT_IN_ZONES_CSV.", "PASS WITH WARNING if all confirmed components reproduce $518.3376 before display rounding."],
        ["TFMX ROAD", "Zone CAN; 677 kg chargeable", "$923.92 PROVISIONAL. Force Majure and Disaster Levy excluded.", "PASS WITH WARNING if confirmed components reproduce the unrounded audit total and both exclusions remain visible."],
        ["KTI GENERAL", "No applicable rate", "NO_RATE; no monetary quote", "PASS if the active path genuinely has no applicable rate."],
        ["STEA ROAD", "No operational zone", "NO_ZONE; no monetary quote", "PASS if no valid zone exists for this destination and required zone type."],
        ["COCHRN ROAD", "No operational zone", "NO_ZONE; no monetary quote", "PASS under the same zone evidence rule."],
        ["TEAMTAS GENERAL", "No operational zone", "NO_ZONE; no monetary quote", "PASS under the same zone evidence rule."],
    ], [28*mm, 47*mm, 55*mm, 45*mm]),
    Spacer(1, 4*mm),
    P("4. Sign-off questions", "H1x"),
    standard_table([
        ["Question", "Yes", "No", "Evidence / comment"],
        ["Do actual weight, rating cubic and maximum length match the request?", "[ ]", "[ ]", ""],
        ["Do TEAMEX and TFMX resolve the expected zones and chargeable weights?", "[ ]", "[ ]", ""],
        ["Can every included amount be traced to an active rule or source line?", "[ ]", "[ ]", ""],
        ["Are unresolved charges excluded and named individually?", "[ ]", "[ ]", ""],
        ["Are provisional and no-quote messages classified correctly?", "[ ]", "[ ]", ""],
        ["Is the result free from fallback to the development workbook?", "[ ]", "[ ]", ""],
    ], [82*mm, 13*mm, 13*mm, 67*mm]),
    Spacer(1, 4*mm),
    ruled_rows(["Final decision", "Tester signature", "Reviewer signature", "Date"]),
]

doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=18*mm, leftMargin=18*mm,
                        topMargin=16*mm, bottomMargin=21*mm,
                        title="Operational Freight Quote Validation Pack",
                        author="Steadfast operational validation")
doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
print(OUT)
