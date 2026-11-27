import streamlit as st
import streamlit.components.v1 as components

from dispatch_generator import html_brief, notices_for, pdf_brief, sms_text, whatsapp_text
from ui import components as C
from ui import theme as T
from ui.messaging import sms_send_panel, textbee_config
from ui.state import ctx

c = ctx()
plan = c.plan
C.page_header("Dispatch center",
              f"Ward-specific notices for the week of {c.target_week}, built from the allocation and routing results.",
              tags=["gen"])
if textbee_config():
    C.alert("info", "SMS can be sent through TextBee; everything else is exported",
            "SMS go out only after you confirm on the SMS tab, and are reported as accepted by TextBee, not delivered. "
            "WhatsApp messages and briefs are generated for officers to send.")
else:
    C.alert("info", "Messages are generated and exported, not sent",
            "No SMS gateway is configured (add a TextBee API key to enable SMS). Download the notices and send them "
            "through your existing channels.")

with C.card():
    a, b, cc = st.columns([1, 2.2, 1])
    cities = sorted(plan["city"].unique()) if c.city == "All cities" else [c.city]
    d_city = a.selectbox("City", cities, key="dc_city")
    city_plan = plan[plan["city"] == d_city].sort_values("priority_rank")
    default = city_plan[city_plan["critical_deficit"] | (city_plan["transferred_out"] > 0)]["ward_id"].tolist()[:3] \
        or city_plan["ward_id"].tolist()[:3]
    wards_sel = b.multiselect("Wards (highest priority first)", city_plan["ward_id"].tolist(), default=default,
                              key=f"dc_wards_{d_city}")
    only_alert = cc.toggle("Only wards needing action", key="dc_only",
                           help="Wards with a supply deficit, a transfer or an unplaced patient")
    if only_alert:
        need = city_plan[city_plan["critical_deficit"] | (city_plan["transferred_out"] > 0)
                         | (city_plan["transferred_in"] > 0) | (city_plan["unresolved_deficit"] > 0)]["ward_id"]
        wards_sel = [w for w in wards_sel if w in set(need)]

if not wards_sel:
    C.empty_state("Select one or more wards to generate notices.")
    st.stop()
notices = notices_for(city_plan[city_plan["ward_id"].isin(wards_sel)], c.R["transfers"])

# ---------------------------------------------------------------- alert preview
C.section("Alert preview", f"{len(notices)} ward(s)")
cols = st.columns(min(3, len(notices)))
for i, n in enumerate(notices):
    s = n["supply"]
    with cols[i % len(cols)]:
        st.markdown(
            f"<div class='fc'><div style='display:flex;justify-content:space-between;align-items:center'>"
            f"<b>{C.esc(n['ward_id'])}</b>{C.risk_badge(n['risk'])}</div>"
            f"<div class='w' style='margin:4px 0 8px 0'>{C.esc(n['city'])} · week of {C.esc(n['target'])}</div>"
            f"<div class='n' style='font-size:24px'>{n['cases']:.1f} <small>cases forecast</small></div>"
            + "".join(f"<div class='r'>{v['label']}: <b>{v['allocated']}</b> / {v['required']}"
                      + (f" <span style='color:{T.RED};font-weight:700'>(−{v['deficit']})</span>" if v['deficit'] else "")
                      + "</div>" for v in s.values())
            + f"<div class='r'>Crews: <b>{n['crews_assigned']}</b> of {n['crews_needed']} needed"
            + (f" · transfer out {n['transferred_out']}" if n['transferred_out'] else "")
            + (f" · receive {n['transferred_in']}" if n['transferred_in'] else "") + "</div>"
            + (f"<div class='r' style='color:{T.RED};font-weight:700;margin-top:8px'>Critical supply deficit</div>"
               if n["deficit_alert"] else "<div class='r' style='color:#7FB069;font-weight:500;margin-top:8px'>"
                                          "Fully supplied</div>")
            + "</div>", unsafe_allow_html=True)
        st.write("")

# ---------------------------------------------------------------- channels
t1, t2, t3 = st.tabs([":material/sms: SMS", ":material/chat: WhatsApp", ":material/description: Commissioner brief"])
with t1:
    cols = st.columns(2)
    for i, n in enumerate(notices):
        txt = sms_text(n)
        seg = -(-len(txt) // 153)
        cols[i % 2].markdown(f"<div class='msg-h'><b>{C.esc(n['ward_id'])}</b><span>{len(txt)} chars · {seg} SMS "
                             f"segment(s) · {C.tag('gen')}</span></div><div class='msg'>{C.esc(txt)}</div>",
                             unsafe_allow_html=True)
        cols[i % 2].write("")
    st.download_button("Download SMS notices (.txt)", "\n\n".join(sms_text(n) for n in notices),
                       f"sms_{d_city}_{c.target_week}.txt", icon=":material/download:")
    st.divider()
    sms_send_panel(notices, d_city)
with t2:
    cols = st.columns(2)
    for i, n in enumerate(notices):
        cols[i % 2].markdown(f"<div class='msg-h'><b>{C.esc(n['ward_id'])}</b>{C.tag('gen')}</div>"
                             f"<div class='msg'>{C.esc(whatsapp_text(n))}</div>", unsafe_allow_html=True)
        cols[i % 2].write("")
    st.download_button("Download WhatsApp notices (.txt)",
                       "\n\n----------\n\n".join(whatsapp_text(n) for n in notices),
                       f"whatsapp_{d_city}_{c.target_week}.txt", icon=":material/download:")
with t3:
    title = f"Commissioner dispatch brief: {d_city}, week of {c.target_week}"
    html = html_brief(notices, title)
    a, b, _ = st.columns([1.2, 1, 3])
    a.download_button("Printable HTML report", html, f"brief_{d_city}_{c.target_week}.html", "text/html",
                      icon=":material/print:")
    pdf = pdf_brief(notices, title)
    if pdf:
        b.download_button("PDF brief", pdf, f"brief_{d_city}_{c.target_week}.pdf", "application/pdf",
                          icon=":material/picture_as_pdf:")
    else:
        b.caption("PDF library not installed; print the HTML report to PDF instead.")
    try:
        components.html(html, height=640, scrolling=True)
    except Exception:
        C.empty_state("Preview unavailable in this Streamlit version; use the downloads above.")

st.divider()
st.download_button("Download full 60-ward dispatch plan (CSV)", plan.to_csv(index=False),
                   f"dispatch_plan_{c.date_str}_{c.horizon}.csv", "text/csv", icon=":material/table_view:")
