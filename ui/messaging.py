"""Optional SMS delivery panel (TextBee) and its helpers, shared by the Dispatch and System Status pages.
Nothing is sent without an explicit confirmation; the core system never imports this module."""
from pathlib import Path

import pandas as pd
import streamlit as st

from dispatch_generator import sms_text, sms_text_short
from integrations import textbee

ROOT = Path(__file__).resolve().parent.parent

CONTACTS_FILE = ROOT / "data" / "ward_contacts.csv"            # local only, git-ignored (personal data)
CONTACTS_EXAMPLE = ROOT / "data" / "ward_contacts.example.csv"


def _secrets():
    try:
        st.secrets.to_dict()          # raises if no secrets file exists
        return st.secrets
    except Exception:
        return None


def textbee_config():
    return textbee.load_config(_secrets())


def load_contacts():
    if "contacts" not in st.session_state:
        src = CONTACTS_FILE if CONTACTS_FILE.exists() else CONTACTS_EXAMPLE
        try:
            c = pd.read_csv(src, dtype=str).fillna("")
        except Exception:
            c = pd.DataFrame(columns=["city", "ward_id", "contact_name", "phone"])
        st.session_state.contacts = c
    return st.session_state.contacts


def sms_send_panel(notices, d_city):
    """Optional real SMS delivery through TextBee. Nothing is sent without an explicit confirmation."""
    st.markdown("#### Send by SMS (TextBee)")
    cfg = textbee_config()
    if cfg is None:
        st.info("Sending is off: no TextBee API key is configured, so notices are generated and exported only. "
                "To enable it, add `TEXTBEE_API_KEY` (and optionally `TEXTBEE_DEVICE_ID`) to "
                "`.streamlit/secrets.toml` or Streamlit Cloud secrets. See README, *SMS delivery with TextBee*.")
        return
    st.caption(f"TextBee configured · device: {cfg['device_id'] or 'default device'} · "
               f"SIM: {cfg.get('sim_subscription_id') or 'phone default'} · gateway: {cfg['base_url']}. "
               "Messages go out from the phone running the TextBee app; normal SMS charges and plan limits apply.")
    fmt = st.radio("Message format", ["single", "full"], horizontal=True, key="sms_fmt",
                   format_func={"single": "Single SMS (max 160 characters, recommended)",
                                "full": "Full notice (usually 2 SMS)"}.get,
                   help="Some phones and carriers fail on multi-part SMS sent by an app (a 'modem' error in "
                        "TextBee). The single format always fits in one plain SMS.")
    make = sms_text_short if fmt == "single" else sms_text
    with st.expander("Preview the message that will be sent"):
        for n in notices:
            t = make(n)
            st.text(f"{n['ward_id']} ({len(t)} chars, {-(-len(t) // 153) if len(t) > 160 else 1} SMS):\n{t}")
    contacts = load_contacts()
    wards = [n["ward_id"] for n in notices]
    cur = contacts.set_index("ward_id") if len(contacts) else pd.DataFrame()
    ed = pd.DataFrame({"ward_id": wards,
                       "contact_name": [cur["contact_name"].get(w, "") if len(cur) else "" for w in wards],
                       "phone": [cur["phone"].get(w, "") if len(cur) else "" for w in wards]})
    edited = st.data_editor(ed, hide_index=True, width="stretch", key=f"sms_contacts_{d_city}_{'-'.join(wards)}",
                            disabled=["ward_id"], column_config={
                                "ward_id": "Ward", "contact_name": "Ward commissioner / officer",
                                "phone": st.column_config.TextColumn("Mobile number",
                                                                     help="e.g. 01712345678 or +8801712345678")})
    edited["number"] = edited["phone"].map(textbee.normalize_phone)
    valid = edited[edited["number"].notna()]
    invalid = edited[edited["phone"].str.strip().ne("") & edited["number"].isna()]
    if len(invalid):
        st.warning("Not a valid mobile number: " + ", ".join(invalid["ward_id"]))
    if st.button("Save contacts for this session", help="Kept in memory. To keep them, copy data/ward_contacts.example.csv "
                                                     "to data/ward_contacts.csv and fill it in (it is git-ignored)."):
        upd = contacts.set_index("ward_id")
        for r in edited.itertuples():
            upd.loc[r.ward_id, ["contact_name", "phone"]] = [r.contact_name, r.phone]
        st.session_state.contacts = upd.reset_index()
        st.success("Contacts saved for this session.")
    if valid.empty:
        st.caption("Enter at least one valid mobile number to enable sending.")
        return
    batch = st.session_state.get("sms_batches", 0)          # new checkbox after every send: confirm again each time
    confirm = st.checkbox(f"I confirm sending {len(valid)} real SMS to the numbers above.", key=f"sms_confirm_{batch}")
    if st.button(f"Send {len(valid)} SMS now", type="primary", disabled=not confirm):
        by_ward = {n["ward_id"]: n for n in notices}
        results = []
        with st.spinner("Sending through TextBee..."):
            for r in valid.itertuples():
                res = textbee.send_sms([r.number], make(by_ward[r.ward_id]), cfg)
                results.append({"time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"), "ward_id": r.ward_id,
                                "number": r.number, "result": "Accepted by TextBee" if res["ok"] else "Failed",
                                "http_status": res["status"], "detail": res["detail"]})
        log = pd.DataFrame(results)
        st.session_state.sms_log = pd.concat([st.session_state.get("sms_log", pd.DataFrame()), log],
                                             ignore_index=True)
        n_ok = int((log["result"] != "Failed").sum())
        (st.success if n_ok == len(log) else st.warning)(
            f"{n_ok} of {len(log)} message(s) accepted by TextBee. 'Accepted' means queued on the phone; "
            "confirm delivery in the TextBee dashboard.")
        st.session_state.sms_batches = batch + 1
    if "sms_log" in st.session_state and len(st.session_state.sms_log):
        st.dataframe(st.session_state.sms_log, hide_index=True, width="stretch")
        st.download_button("Download send log (CSV)", st.session_state.sms_log.to_csv(index=False),
                           "sms_send_log.csv", "text/csv")
