"""Ward-specific dispatch notices from local, deterministic templates (no LLM, no network).

Formats: SMS text, WhatsApp text (with *bold* markup), printable HTML commissioner brief and PDF brief.
Every number comes straight from the allocation and routing tables, so a notice always matches the dashboard.
Sending is out of scope: notices are generated and exported for officers to send through existing channels.
"""
import html
from datetime import datetime

from config import HORIZON_NAME

SUPPLY = (("saline_bags_needed", "Saline bags", "Saline"), ("diagnostic_kits_needed", "Diagnostic kits", "Kits"),
          ("hospital_beds_required", "Hospital beds", "Beds"))
REQUIRED_FIELDS = ("city", "ward_id", "forecast_origin_week", "target_week", "horizon", "predicted_cases",
                   "risk", "crews_assigned", "crews_needed", "bed_capacity", "transferred_out", "transferred_in",
                   "unresolved_deficit") + tuple(f"{r}_{k}" for r, _, _ in SUPPLY
                                                 for k in ("required", "allocated", "deficit"))


def _transfer_lines(ward_id, transfers):
    out = transfers[transfers["from_ward"] == ward_id] if len(transfers) else transfers
    inn = transfers[transfers["to_ward"] == ward_id] if len(transfers) else transfers
    sent = [f"{r.to_ward} ({int(r.patients)})" for r in out.itertuples()]
    recv = [f"{r.from_ward} ({int(r.patients)})" for r in inn.itertuples()]
    return sent, recv


def build_notice(row, transfers):
    """Structured notice (a dict) for one ward from a row of pipeline plan output."""
    missing = [f for f in REQUIRED_FIELDS if f not in row]
    if missing:
        raise ValueError(f"Plan row is missing fields: {missing}")
    sent, recv = _transfer_lines(row["ward_id"], transfers)
    supply = {}
    for r, label, short in SUPPLY:
        supply[short] = {"label": label, "required": int(row[f"{r}_required"]),
                         "allocated": int(row[f"{r}_allocated"]), "deficit": int(row[f"{r}_deficit"])}
    deficit_any = any(v["deficit"] > 0 for v in supply.values())

    actions = []
    if supply["Saline"]["deficit"] or supply["Kits"]["deficit"]:
        actions.append(f"Supply shortfall: request {supply['Saline']['deficit']} saline bags and "
                       f"{supply['Kits']['deficit']} diagnostic kits from the city reserve; prioritise severe cases.")
    if int(row["transferred_out"]):
        actions.append(f"Arrange transfer of {int(row['transferred_out'])} patient(s) to: {', '.join(sent)}.")
    if int(row["unresolved_deficit"]):
        actions.append(f"ESCALATE: {int(row['unresolved_deficit'])} patient(s) have no bed in {row['city']}; "
                       "request surge beds from the city health office.")
    if int(row["transferred_in"]):
        actions.append(f"Prepare {int(row['transferred_in'])} bed(s) for incoming patients from: {', '.join(recv)}.")
    if int(row["crews_assigned"]):
        actions.append(f"Deploy {int(row['crews_assigned'])} spraying crew(s) to larvicide standing water and "
                       "clear breeding sites.")
    if int(row["crews_needed"]) > int(row["crews_assigned"]):
        actions.append(f"Crew shortfall: {int(row['crews_needed']) - int(row['crews_assigned'])} more crew(s) "
                       "requested; mobilise community clean-up.")
    if not actions:
        actions.append("Routine surveillance; no additional resources required this period.")

    return {
        "city": row["city"], "ward_id": row["ward_id"], "origin": row["forecast_origin_week"],
        "target": row["target_week"], "horizon": HORIZON_NAME.get(row["horizon"], row["horizon"]),
        "cases": float(row["predicted_cases"]), "risk": row["risk"], "supply": supply,
        "deficit_alert": deficit_any, "crews_assigned": int(row["crews_assigned"]),
        "crews_needed": int(row["crews_needed"]), "bed_capacity": int(row["bed_capacity"]),
        "transferred_out": int(row["transferred_out"]), "transferred_in": int(row["transferred_in"]),
        "unresolved_beds": int(row["unresolved_deficit"]), "sent_to": sent, "received_from": recv,
        "actions": actions,
    }


def sms_text(n):
    s = n["supply"]
    parts = [f"DENGUE ALERT {n['ward_id']}, {n['city']}: {n['risk'].upper()} risk, ~{n['cases']:.0f} cases "
             f"wk of {n['target']} ({n['horizon']} ahead)."]
    parts.append("Alloc/Need: " + ", ".join(f"{k} {v['allocated']}/{v['required']}" for k, v in s.items()) + ".")
    if n["deficit_alert"]:
        parts.append("DEFICIT: " + ", ".join(f"{k} -{v['deficit']}" for k, v in s.items() if v["deficit"]) + ".")
    parts.append(f"Crews: {n['crews_assigned']}.")
    if n["transferred_out"]:
        parts.append(f"Transfer {n['transferred_out']} pt to {', '.join(n['sent_to'])}.")
    if n["unresolved_beds"]:
        parts.append(f"{n['unresolved_beds']} pt no bed: ESCALATE.")
    if n["transferred_in"]:
        parts.append(f"Receive {n['transferred_in']} pt.")
    return " ".join(parts)


def whatsapp_text(n):
    s = n["supply"]
    icon = {"Low": "🟢", "Medium": "🟡", "High": "🟠", "Critical": "🔴"}.get(n["risk"], "")
    lines = [f"*Dengue dispatch: {n['ward_id']} ({n['city']})*",
             f"{icon} Risk: *{n['risk']}*  |  Forecast: *{n['cases']:.1f} cases* in week of {n['target']}",
             f"Horizon: {n['horizon']} (data up to week of {n['origin']})", "",
             "*Supplies (allocated / required, deficit)*"]
    for v in s.values():
        flag = " ⚠️" if v["deficit"] else ""
        lines.append(f"• {v['label']}: {v['allocated']} / {v['required']}, deficit {v['deficit']}{flag}")
    lines += ["", f"*Spraying crews:* {n['crews_assigned']} assigned (needed {n['crews_needed']})",
              f"*Hospital beds:* local capacity {n['bed_capacity']}"]
    if n["sent_to"]:
        lines.append(f"↪️ Transfer out: {', '.join(n['sent_to'])}")
    if n["received_from"]:
        lines.append(f"↩️ Receiving from: {', '.join(n['received_from'])}")
    if n["unresolved_beds"]:
        lines.append(f"🚨 Unplaced patients: {n['unresolved_beds']}")
    if n["deficit_alert"]:
        lines += ["", "🚨 *CRITICAL SUPPLY DEFICIT*: demand cannot be fully met at current regional stock."]
    lines += ["", "*Action required:*"] + [f"{i}. {a}" for i, a in enumerate(n["actions"], 1)]
    lines += ["", "_Generated offline by the dengue early-warning system. Figures are model forecasts._"]
    return "\n".join(lines)


_CSS = """
:root{color-scheme:light}
html,body{background:#ffffff !important;color:#111 !important}
body{font-family:Arial,Helvetica,sans-serif;margin:24px;}
.card,table,td,th,div,li,h1,h2{color:#111}
.card{background:#ffffff}
h1{font-size:20px;margin:0 0 4px 0} .sub{color:#555;font-size:12px;margin-bottom:14px}
.card{border:1px solid #bbb;border-radius:6px;padding:12px 14px;margin:0 0 16px 0;page-break-inside:avoid}
.card h2{font-size:16px;margin:0 0 6px 0} table{border-collapse:collapse;width:100%;font-size:12px;margin:6px 0}
th,td{border:1px solid #ccc;padding:4px 6px;text-align:left} th{background:#eee}
.alert{background:#fde2e1;border:1px solid #c62828;color:#8b0000;padding:6px 8px;border-radius:4px;font-weight:bold;font-size:12px}
.risk{display:inline-block;padding:2px 8px;border-radius:4px;font-weight:bold;font-size:12px}
.Low{background:#c8e6c9}.Medium{background:#fff59d}.High{background:#ffcc80}.Critical{background:#ef9a9a}
ol{font-size:12px;margin:4px 0 0 18px;padding:0} .foot{font-size:10px;color:#666;margin-top:10px}
@media print{body{margin:10mm}}
"""


def html_brief(notices, title="Commissioner dispatch brief"):
    esc = html.escape
    cards = []
    for n in notices:
        rows = "".join(f"<tr><td>{esc(v['label'])}</td><td>{v['required']}</td><td>{v['allocated']}</td>"
                       f"<td>{v['deficit']}</td></tr>" for v in n["supply"].values())
        alert = ("<div class='alert'>CRITICAL SUPPLY DEFICIT: demand cannot be fully met at current stock</div>"
                 if n["deficit_alert"] else "")
        beds = (f"Local bed capacity {n['bed_capacity']}; transferred out {n['transferred_out']}"
                + (f" to {esc(', '.join(n['sent_to']))}" if n["sent_to"] else "")
                + f"; receiving {n['transferred_in']}"
                + (f" from {esc(', '.join(n['received_from']))}" if n["received_from"] else "")
                + f"; unplaced patients {n['unresolved_beds']}.")
        acts = "".join(f"<li>{esc(a)}</li>" for a in n["actions"])
        cards.append(
            f"<div class='card'><h2>{esc(n['ward_id'])}, {esc(n['city'])} "
            f"<span class='risk {esc(n['risk'])}'>{esc(n['risk'])}</span></h2>"
            f"<div>Forecast <b>{n['cases']:.1f} cases</b> in the week of {esc(n['target'])} "
            f"({esc(n['horizon'])} ahead; data up to the week of {esc(n['origin'])}).</div>{alert}"
            f"<table><tr><th>Supply</th><th>Required</th><th>Allocated</th><th>Deficit</th></tr>{rows}</table>"
            f"<div style='font-size:12px'><b>Spraying crews:</b> {n['crews_assigned']} assigned "
            f"(needed {n['crews_needed']}). <b>Beds:</b> {beds}</div>"
            f"<div style='font-size:12px;margin-top:6px'><b>Action required</b></div><ol>{acts}</ol></div>")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (f"<!doctype html><html style='background:#fff'><head><meta charset='utf-8'><meta name='color-scheme' content='light'><title>{esc(title)}</title><style>{_CSS}</style>"
            f"</head><body><h1>{esc(title)}</h1><div class='sub'>Generated {stamp} locally by the dengue "
            f"early-warning system. Forecasts are model estimates; bed capacities are demo assumptions until "
            f"replaced with verified figures.</div>{''.join(cards)}</body></html>")


def _latin1(text):
    repl = {"–": "-", "—": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "…": "...", "×": "x", "≈": "~"}
    for a, b in repl.items():
        text = text.replace(a, b)
    return text.encode("latin-1", "replace").decode("latin-1")


def pdf_brief(notices, title="Commissioner dispatch brief"):
    """PDF bytes, or None if the optional fpdf2 package is not installed (HTML brief still works)."""
    try:
        from fpdf import FPDF
    except ImportError:
        return None
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, _latin1(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.multi_cell(0, 4, _latin1("Generated locally by the dengue early-warning system. Forecasts are model "
                                 "estimates; bed capacities are demo assumptions until replaced with verified "
                                 "figures."), new_x="LMARGIN", new_y="NEXT")
    for n in notices:
        if pdf.get_y() > 230:
            pdf.add_page()
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 6, _latin1(f"{n['ward_id']}, {n['city']}  |  Risk: {n['risk']}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 4.5, _latin1(f"Forecast {n['cases']:.1f} cases in the week of {n['target']} "
                                       f"({n['horizon']} ahead; data up to the week of {n['origin']})."),
                       new_x="LMARGIN", new_y="NEXT")
        if n["deficit_alert"]:
            pdf.set_text_color(160, 0, 0)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 5, "CRITICAL SUPPLY DEFICIT: demand cannot be fully met at current stock",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "B", 9)
        for head, w in (("Supply", 60), ("Required", 30), ("Allocated", 30), ("Deficit", 30)):
            pdf.cell(w, 5, head, border=1)
        pdf.ln()
        pdf.set_font("Helvetica", "", 9)
        for v in n["supply"].values():
            for val, w in ((v["label"], 60), (v["required"], 30), (v["allocated"], 30), (v["deficit"], 30)):
                pdf.cell(w, 5, _latin1(str(val)), border=1)
            pdf.ln()
        beds = (f"Spraying crews: {n['crews_assigned']} assigned (needed {n['crews_needed']}). Beds: local capacity "
                f"{n['bed_capacity']}, transferred out {n['transferred_out']}"
                + (f" to {', '.join(n['sent_to'])}" if n["sent_to"] else "")
                + f", receiving {n['transferred_in']}, unplaced {n['unresolved_beds']}.")
        pdf.multi_cell(0, 4.5, _latin1(beds), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, "Action required", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for i, a in enumerate(n["actions"], 1):
            pdf.multi_cell(0, 4.5, _latin1(f"{i}. {a}"), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def notices_for(plan, transfers, ward_ids=None):
    rows = plan if ward_ids is None else plan[plan["ward_id"].isin(ward_ids)]
    return [build_notice(r, transfers) for r in rows.to_dict("records")]
