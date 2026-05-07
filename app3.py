import streamlit as st
import pandas as pd
import json
import qrcode
import io
import os
import zipfile
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

st.set_page_config(
    page_title="RFID·QR Material Manager",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

DATA_FILE   = "material_data.json"
MASTER_FILE = "master_data.json"   # persisted master CSV on server

# ─────────────────────────────────────────────
# DATA STORAGE
# ─────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_master():
    """Load persisted master CSV (list of dicts)."""
    if os.path.exists(MASTER_FILE):
        with open(MASTER_FILE, "r") as f:
            return json.load(f)
    return []

def save_master(records):
    with open(MASTER_FILE, "w") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

def get_master_df():
    """Return master as a DataFrame, or None."""
    records = load_master()
    if not records:
        return None
    return pd.DataFrame(records)

# ─────────────────────────────────────────────
# URL HELPER
# ─────────────────────────────────────────────
DEFAULT_APP_URL = "https://rfidmockupv3-ctou6fm5nvvhue75tscegg.streamlit.app"

def get_base_url():
    if st.session_state.get("base_url"):
        return st.session_state["base_url"].rstrip("/")
    try:
        url = st.secrets.get("base_url", "")
        if url:
            return url.rstrip("/")
    except:
        pass
    return DEFAULT_APP_URL

def tag_url(rfid_tag_code):
    return f"{get_base_url()}?tag={rfid_tag_code}"

# ─────────────────────────────────────────────
# QR CODE GENERATOR
# ─────────────────────────────────────────────
def make_qr_image(url, label_top, label_bot="Scan for material info"):
    qr = qrcode.QRCode(version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    label_h = 56
    canvas = Image.new("RGB", (qr_img.width, qr_img.height + label_h), "white")
    canvas.paste(qr_img, (0, 0))
    draw = ImageDraw.Draw(canvas)
    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
        font_sm  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    except:
        font_big = ImageFont.load_default()
        font_sm  = font_big
    bbox = draw.textbbox((0,0), label_top, font=font_big)
    draw.text(((qr_img.width-(bbox[2]-bbox[0]))//2, qr_img.height+5), label_top, fill="black", font=font_big)
    bbox2 = draw.textbbox((0,0), label_bot, font=font_sm)
    draw.text(((qr_img.width-(bbox2[2]-bbox2[0]))//2, qr_img.height+26), label_bot, fill="#555555", font=font_sm)
    tag_lbl = "RFID·QR SYSTEM"
    bbox3 = draw.textbbox((0,0), tag_lbl, font=font_sm)
    draw.text(((qr_img.width-(bbox3[2]-bbox3[0]))//2, qr_img.height+42), tag_lbl, fill="#888888", font=font_sm)
    return canvas

def qr_to_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()

# ─────────────────────────────────────────────
# FIELD CONFIG
# ─────────────────────────────────────────────
EXPECTED_COLS = [
    "Material", "Plant", "Storage Location", "Storage Type",
    "Storage Section", "Storage Bin", "Material Description",
    "Batch", "Stock Category", "Total Stock",
    "Base Unit of Measure", "SLED/BBD", "GR Date", "RFID Tag Code"
]

DROPDOWN_FIELDS = [
    "Material", "Plant", "Storage Location", "Storage Type",
    "Storage Section", "Stock Category", "Base Unit of Measure", "Storage Bin"
]

def get_field_options(data, field):
    vals = set()
    for rec in data.values():
        v = rec.get(field, "").strip()
        if v and not v.startswith("_"):
            vals.add(v)
    return sorted(vals)

def parse_csv_generic(uploaded_file):
    try:
        df = pd.read_csv(uploaded_file, dtype=str).fillna("")
        df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]
        return df, None
    except Exception as e:
        return None, str(e)

def parse_csv(uploaded_file):
    df, err = parse_csv_generic(uploaded_file)
    if err:
        return None, err
    if "RFID Tag Code" not in df.columns:
        return None, "CSV missing 'RFID Tag Code' column"
    df = df[df["RFID Tag Code"].str.strip() != ""]
    return df, None

# ─────────────────────────────────────────────
# MASTER LIST HELPERS
# ─────────────────────────────────────────────
def master_display_opts(master_df):
    """Build display list 'MaterialID | Description' for selectbox."""
    mat_col   = next((c for c in master_df.columns if "Material Description" in c), None)
    matid_col = next((c for c in master_df.columns if c.strip() == "Material"), None)
    if matid_col and mat_col:
        return ["— choose material —"] + [
            f"{row[matid_col]} | {row[mat_col]}" for _, row in master_df.iterrows()
        ]
    elif matid_col:
        return ["— choose material —"] + master_df[matid_col].tolist()
    return ["— choose material —"] + [f"Row {i+1}" for i in range(len(master_df))]

def prefill_from_master(master_df, chosen, display_opts):
    """Return dict of field values from the chosen master row."""
    if chosen == "— choose material —":
        return {}
    idx = display_opts.index(chosen) - 1
    row = master_df.iloc[idx]
    return {col: str(row.get(col, "")).strip()
            for col in EXPECTED_COLS if col in master_df.columns}

# ─────────────────────────────────────────────
# PASSWORD HELPERS
# ─────────────────────────────────────────────
DEFAULT_PASSWORD = "RFID123"

def get_password():
    return os.environ.get("RFID_PASSWORD",
           st.session_state.get("app_password", DEFAULT_PASSWORD))

def check_viewer_auth(tag_code):
    return st.session_state.get(f"auth_ok_{tag_code}", False)

def show_password_gate(tag_code):
    st.markdown("""
    <div style="background:#0f1a2e;border:1.5px solid #2a4a7a;border-radius:14px;
        padding:1.5rem 1.5rem 1.2rem;margin-top:0.5rem;">
      <div style="font-size:1rem;font-weight:700;color:#4f9cf9;margin-bottom:0.4rem;">
          🔒 Warehouse Authentication</div>
      <div style="font-size:0.88rem;color:#7a8299;margin-bottom:1rem;">
          Enter the warehouse password to edit or clear this tag.</div>
    </div>
    """, unsafe_allow_html=True)
    pw = st.text_input("Password", type="password", placeholder="Enter password…",
                       key=f"pw_input_{tag_code}", label_visibility="collapsed")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔓 Unlock", use_container_width=True, type="primary",
                     key=f"pw_submit_{tag_code}"):
            if pw == get_password():
                st.session_state[f"auth_ok_{tag_code}"] = True
                st.success("✅ Authenticated!")
                st.rerun()
            else:
                st.error("❌ Incorrect password.")
    with c2:
        if st.button("✕ Cancel", use_container_width=True, key=f"pw_cancel_{tag_code}"):
            st.session_state.pop(f"v_mode_{tag_code}", None)
            st.rerun()

# ─────────────────────────────────────────────
# SHARED EDIT / REGISTER FORM
# ─────────────────────────────────────────────
def _show_edit_form(tag_code, rec, data, is_empty=False):
    """
    Step-by-step edit/register form:
    Step 1 — Choose mode: Master DB or Manual
    Step 2 (Master) — Search & select material → load form
    Step 3 — Edit fields → Save
    """
    title = "Register Material" if is_empty else "Edit Material"
    st.markdown(f"""
    <div class="edit-header">
      <div class="edit-header-title">✎  {title} — {tag_code}</div>
      <div class="edit-header-sub">Follow the steps below to fill in material information.</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Session state keys ────────────────────────────────────
    mode_key   = f"ef_mode_{tag_code}"      # "master" or "manual"
    loaded_key = f"ef_loaded_{tag_code}"    # dict of loaded field values (after selecting)
    form_key   = f"ef_form_{tag_code}"      # True when form should show

    master_df  = get_master_df()

    # ══════════════════════════════════════════════════════════
    # STEP 1 — Choose mode
    # ══════════════════════════════════════════════════════════
    if mode_key not in st.session_state:
        st.markdown("### Step 1 — How would you like to fill in the information?")
        st.markdown(" ")
        c1, c2 = st.columns(2)
        with c1:
            master_disabled = master_df is None
            hint = "" if not master_disabled else " *(no master list uploaded)*"
            if st.button(
                f"📋 From Master Database{hint}",
                use_container_width=True,
                type="primary",
                disabled=master_disabled,
                key=f"ef_btn_master_{tag_code}"
            ):
                st.session_state[mode_key] = "master"
                st.rerun()
        with c2:
            if st.button(
                "✏️ Fill Manually",
                use_container_width=True,
                key=f"ef_btn_manual_{tag_code}"
            ):
                # Load existing rec values for manual edit
                st.session_state[mode_key]   = "manual"
                st.session_state[loaded_key] = {f: rec.get(f,"") for f in EXPECTED_COLS}
                st.session_state[form_key]   = True
                st.rerun()

        if master_disabled:
            st.info("💡 Upload a Master Material CSV in **Setup** tab to enable database selection.")
        return

    mode = st.session_state[mode_key]

    # ══════════════════════════════════════════════════════════
    # STEP 2 (Master mode) — Search & select material
    # ══════════════════════════════════════════════════════════
    if mode == "master" and not st.session_state.get(form_key):
        st.markdown("### Step 2 — Search & select material from Master Database")
        st.caption(f"{len(master_df)} materials in master list")

        # Search box
        search_q = st.text_input(
            "Search material",
            placeholder="Type material ID, description, plant...",
            key=f"ef_search_{tag_code}"
        )

        # Filter master_df
        if search_q.strip():
            q = search_q.strip().lower()
            mask = master_df.apply(
                lambda row: any(q in str(v).lower() for v in row.values), axis=1
            )
            filtered = master_df[mask]
        else:
            filtered = master_df

        st.caption(f"{len(filtered)} results")

        if len(filtered) == 0:
            st.warning("No materials match your search.")
        else:
            # Build display list
            mat_col   = next((c for c in filtered.columns if "Material Description" in c), None)
            matid_col = next((c for c in filtered.columns if c.strip() == "Material"), None)

            if matid_col and mat_col:
                options = ["— select material —"] + [
                    f"{row[matid_col]}  |  {row[mat_col]}"
                    for _, row in filtered.iterrows()
                ]
            elif matid_col:
                options = ["— select material —"] + filtered[matid_col].tolist()
            else:
                options = ["— select material —"] + [f"Row {i+1}" for i in range(len(filtered))]

            chosen = st.selectbox(
                "Select material",
                options=options,
                key=f"ef_chosen_{tag_code}",
                label_visibility="collapsed"
            )

            st.markdown(" ")
            c_load, c_back = st.columns([2, 1])
            with c_load:
                if st.button("✅ Load this material into form",
                             use_container_width=True, type="primary",
                             key=f"ef_load_{tag_code}",
                             disabled=(chosen == "— select material —")):
                    # Find actual row and load values
                    idx = options.index(chosen) - 1
                    row = filtered.iloc[idx]
                    loaded = {f: str(row.get(f,"")).strip()
                              for f in EXPECTED_COLS if f in filtered.columns}
                    # Keep RFID Tag Code from tag_code
                    loaded["RFID Tag Code"] = tag_code
                    st.session_state[loaded_key] = loaded
                    st.session_state[form_key]   = True
                    st.rerun()
            with c_back:
                if st.button("← Back", use_container_width=True,
                             key=f"ef_back_step2_{tag_code}"):
                    st.session_state.pop(mode_key, None)
                    st.rerun()
        return

    # ══════════════════════════════════════════════════════════
    # STEP 3 — Edit form + Save
    # ══════════════════════════════════════════════════════════
    loaded = st.session_state.get(loaded_key, {f: rec.get(f,"") for f in EXPECTED_COLS})

    if mode == "master":
        mat_name = loaded.get("Material Description", loaded.get("Material",""))
        st.markdown(f"### Step 3 — Review & Edit")
        st.success(f"📋 Loaded from Master: **{mat_name}**")
    else:
        st.markdown("### Fill in material information")

    st.markdown(f"**RFID Tag Code (fixed):** `{tag_code}`")
    st.markdown("---")

    # ── Widget keys (use wk_ prefix, populated from loaded) ──
    # On first render of step 3, clear widget keys so loaded values take effect
    first_render_key = f"ef_first_{tag_code}"
    if first_render_key not in st.session_state:
        for field in EXPECTED_COLS:
            if field == "RFID Tag Code": continue
            for sfx in ["_sel","_custom","_txt"]:
                st.session_state.pop(f"wk_{tag_code}_{field}{sfx}", None)
        st.session_state[first_render_key] = True

    col_a, col_b = st.columns(2)
    for j, field in enumerate(EXPECTED_COLS):
        if field == "RFID Tag Code": continue
        wk = f"wk_{tag_code}_{field}"
        val = loaded.get(field, "")
        target = col_a if j % 2 == 0 else col_b
        with target:
            if field in DROPDOWN_FIELDS:
                options = get_field_options(data, field)
                if val and val not in options:
                    options = sorted(options + [val])
                CUSTOM = "— type custom value —"
                choices = options + [CUSTOM]
                idx = options.index(val) if val in options else len(choices)-1
                sel = st.selectbox(field, choices, index=idx, key=f"{wk}_sel")
                if sel == CUSTOM:
                    st.text_input(f"Custom {field}",
                        value=val, key=f"{wk}_custom",
                        placeholder=f"Enter {field}...")
            else:
                st.text_input(field, value=val, key=f"{wk}_txt")

    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.9rem;color:#7a8299;margin-bottom:6px;'>"
        "Type <b style='color:#4f9cf9;font-size:1rem;'>SAVE</b> to confirm.</div>",
        unsafe_allow_html=True)
    confirm_txt = st.text_input("Confirm",
        placeholder="Type SAVE here…",
        key=f"ef_confirm_{tag_code}", label_visibility="collapsed")

    btn_c1, btn_c2, btn_c3 = st.columns([2, 2, 1])
    with btn_c1:
        save_clicked = st.button("💾 Save Material", type="primary",
            use_container_width=True, key=f"ef_save_{tag_code}")
    with btn_c2:
        # Allow going back to re-search (master mode only)
        if mode == "master":
            if st.button("🔍 Change material", use_container_width=True,
                         key=f"ef_change_{tag_code}"):
                st.session_state.pop(loaded_key, None)
                st.session_state.pop(form_key, None)
                st.session_state.pop(first_render_key, None)
                st.rerun()
    with btn_c3:
        cancel_clicked = st.button("✕ Cancel", use_container_width=True,
            key=f"ef_cancel_{tag_code}")

    def _cleanup():
        for field in EXPECTED_COLS:
            if field == "RFID Tag Code": continue
            wk = f"wk_{tag_code}_{field}"
            for sfx in ["_sel","_custom","_txt"]:
                st.session_state.pop(f"{wk}{sfx}", None)
        for k in [mode_key, loaded_key, form_key, first_render_key,
                  f"ef_confirm_{tag_code}", f"ef_search_{tag_code}",
                  f"ef_chosen_{tag_code}", f"v_mode_{tag_code}",
                  f"auth_ok_{tag_code}", f"v_register_{tag_code}"]:
            st.session_state.pop(k, None)

    if save_clicked:
        if confirm_txt.strip().upper() != "SAVE":
            st.error("⚠️ Type SAVE in the confirmation box to proceed.")
        else:
            new_vals = {"RFID Tag Code": tag_code}
            for field in EXPECTED_COLS:
                if field == "RFID Tag Code": continue
                wk = f"wk_{tag_code}_{field}"
                if field in DROPDOWN_FIELDS:
                    sv = st.session_state.get(f"{wk}_sel", "")
                    new_vals[field] = (st.session_state.get(f"{wk}_custom","")
                                      if sv == "— type custom value —" else sv)
                else:
                    new_vals[field] = st.session_state.get(f"{wk}_txt", "")
            new_vals["_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data[tag_code] = new_vals
            save_data(data)
            _cleanup()
            st.success(f"✅ Tag {tag_code} saved successfully!")
            st.rerun()

    if cancel_clicked:
        _cleanup()
        st.rerun()


def show_viewer(tag_code):
    data = load_data()

    st.markdown("""
    <style>
    #MainMenu, footer, header {visibility: hidden;}
    .block-container {padding-top: 0 !important; padding-bottom: 2rem; max-width: 680px;}
    .stButton > button {font-size: 1.05rem !important; padding: 0.65rem 1rem !important; border-radius: 10px !important;}
    div[data-testid="stForm"] {border: none; padding: 0;}
    .mat-id-box { background: linear-gradient(135deg,#0f2a52,#1a1040); border: 1px solid #3a5a9a; border-radius: 14px; padding: 1.2rem 1.4rem; margin-bottom: 1rem; }
    .mat-id-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 2px; color: #7a8299; margin-bottom: 6px; }
    .mat-id-value { font-family: monospace; font-size: 2.1rem; font-weight: 800; color: #4f9cf9; letter-spacing: 2px; line-height: 1.1; word-break: break-all; }
    .mat-name-value { font-size: 1.2rem; font-weight: 600; color: #111111; margin-top: 8px; line-height: 1.4; }
    .rfid-tag-badge { display: inline-block; margin-top: 10px; background: rgba(79,156,249,0.15); border: 1px solid #3a5a9a; border-radius: 6px; padding: 4px 10px; font-family: monospace; font-size: 0.72rem; color: #7ab8f5; letter-spacing: 1px; word-break: break-all; }
    .detail-card { background: #f5f7fa; border: 1px solid #c8d0e0; border-radius: 14px; overflow: hidden; margin-bottom: 1rem; }
    .detail-card-header { background: #dde3ee; padding: 0.6rem 1.1rem; border-bottom: 1px solid #c8d0e0; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 2px; color: #334466; font-weight: 600; }
    .detail-row { display: flex; align-items: center; padding: 0.75rem 1.1rem; border-bottom: 1px solid #dde3ee; gap: 0.8rem; }
    .detail-row:last-child { border-bottom: none; }
    .detail-icon { font-size: 1.25rem; width: 30px; text-align: center; flex-shrink: 0; }
    .detail-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 1px; color: #667799; margin-bottom: 3px; }
    .detail-value { font-size: 1.05rem; font-weight: 600; color: #111111; word-break: break-word; }
    .detail-value-hi { font-size: 1.15rem; font-weight: 700; color: #0a7a45; word-break: break-word; }
    .confirm-box { background: #2a1010; border: 2px solid #f87171; border-radius: 12px; padding: 1.2rem 1.4rem; margin-top: 0.8rem; }
    .confirm-title { font-size: 1.1rem; font-weight: 700; color: #f87171; margin-bottom: 0.5rem; }
    .confirm-body { color: #e8ecf4; font-size: 1rem; line-height: 1.7; }
    .empty-box { background: #1a1d27; border: 2px solid #fbbf24; border-radius: 12px; padding: 2rem; text-align: center; margin-bottom: 1.5rem; }
    .empty-title { font-size: 1.3rem; font-weight: 700; color: #fbbf24; }
    .empty-sub { color: #7a8299; margin-top: 0.5rem; font-size: 0.95rem; }
    .edit-header { background: #0f2240; border: 1px solid #2a4a7a; border-radius: 10px; padding: 0.9rem 1.2rem; margin-bottom: 1rem; }
    .edit-header-title { font-size: 1rem; font-weight: 700; color: #4f9cf9; }
    .edit-header-sub { font-size: 0.82rem; color: #7a8299; margin-top: 4px; line-height: 1.6; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#0a1628,#15103a);
        padding:1.3rem 1.5rem 1.1rem;margin-bottom:1rem;border-bottom:3px solid #4f9cf9;">
      <div style="font-family:monospace;color:#4f9cf9;font-size:0.78rem;letter-spacing:3px;margin-bottom:5px;">📦 RFID · QR SYSTEM</div>
      <div style="font-size:0.8rem;color:#7a8299;letter-spacing:1px;text-transform:uppercase;">RFID Tag</div>
      <div style="font-family:monospace;font-size:1.1rem;font-weight:700;color:#ffffff;letter-spacing:1px;margin-top:4px;word-break:break-all;">{tag_code}</div>
    </div>
    """, unsafe_allow_html=True)

    if not data:
        st.warning("⚠️ No materials registered yet.")
        st.info("Ask your administrator to import data in the Register tab.")
        return

    if tag_code not in data:
        st.error(f"❌ Tag **{tag_code}** not registered.")
        st.info("Contact your warehouse administrator.")
        return

    rec = data[tag_code]

    # ── Empty / cleared ───────────────────────────────────────
    if rec.get("_cleared"):
        st.markdown(f"""
        <div class="empty-box">
          <div style="font-size:3rem;margin-bottom:0.5rem;">📭</div>
          <div class="empty-title">Tag is Empty</div>
          <div class="empty-sub">No material registered<br>Cleared: {rec.get("_cleared_at","unknown")}</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("### Register new material to this tag")
        if not st.session_state.get(f"v_register_{tag_code}", False):
            if st.button("✎  Register Material", use_container_width=True,
                         type="primary", key=f"v_reg_btn_{tag_code}"):
                st.session_state[f"v_register_{tag_code}"] = True
                st.session_state.pop(f"auth_ok_{tag_code}", None)
                st.rerun()
        else:
            if not check_viewer_auth(tag_code):
                show_password_gate(tag_code)
            else:
                _show_edit_form(tag_code, rec, data, is_empty=True)
        return

    # ── Material hero ─────────────────────────────────────────
    st.markdown(f"""
    <div class="mat-id-box">
      <div class="mat-id-label">Material ID</div>
      <div class="mat-id-value">{rec.get("Material","—")}</div>
      <div class="mat-name-value">{rec.get("Material Description","—")}</div>
      <div class="rfid-tag-badge">🏷 RFID: {tag_code}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Detail rows ───────────────────────────────────────────
    st.markdown('<div class="detail-card"><div class="detail-card-header">Material Details</div>', unsafe_allow_html=True)
    stock_val = f"{rec.get('Total Stock','')} {rec.get('Base Unit of Measure','')}".strip()
    rows = [
        ("📦","Storage Bin",     rec.get("Storage Bin",""),     False),
        ("🏭","Plant",           rec.get("Plant",""),           False),
        ("📍","Storage Location",rec.get("Storage Location",""),False),
        ("🗂", "Storage Type",    rec.get("Storage Type",""),    False),
        ("📂","Storage Section", rec.get("Storage Section",""), False),
        ("🏷", "Batch",           rec.get("Batch",""),           False),
        ("📋","Stock Category",  rec.get("Stock Category",""),  False),
        ("📊","Total Stock",     stock_val,                     True),
        ("📅","SLED / BBD",      rec.get("SLED/BBD",""),        False),
        ("📅","GR Date",         rec.get("GR Date",""),         False),
    ]
    for icon, label, value, hi in rows:
        css = "detail-value-hi" if hi else "detail-value"
        st.markdown(f"""<div class="detail-row">
          <div class="detail-icon">{icon}</div>
          <div style="flex:1;min-width:0;">
            <div class="detail-label">{label}</div>
            <div class="{css}">{value or "—"}</div>
          </div>
        </div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    st.caption(f"🕐 Last updated: {rec.get('_updated_at','unknown')}  ·  Scan again to refresh")

    # ── Warehouse actions ─────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Warehouse Actions")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✎  Edit Material", use_container_width=True, type="primary",
                     key=f"v_edit_{tag_code}"):
            st.session_state[f"v_mode_{tag_code}"] = "edit"
            st.session_state.pop(f"auth_ok_{tag_code}", None)
            st.rerun()
    with c2:
        if st.button("🗑  Clear Tag", use_container_width=True,
                     key=f"v_clear_btn_{tag_code}"):
            st.session_state[f"v_mode_{tag_code}"] = "confirm_clear"
            st.session_state.pop(f"auth_ok_{tag_code}", None)
            st.rerun()

    mode = st.session_state.get(f"v_mode_{tag_code}", "")

    if mode in ("edit", "confirm_clear"):
        if not check_viewer_auth(tag_code):
            st.markdown("---")
            show_password_gate(tag_code)
            return

    if mode == "confirm_clear":
        st.markdown(f"""
        <div class="confirm-box">
          <div class="confirm-title">⚠️  Confirm Clear Tag</div>
          <div class="confirm-body">
            Remove all data from RFID tag <strong>{tag_code}</strong><br><br>
            QR code and URL will remain unchanged.<br><strong>Are you sure?</strong>
          </div>
        </div>""", unsafe_allow_html=True)
        st.markdown(" ")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("✅  Yes, Clear Tag", use_container_width=True, type="primary",
                         key=f"v_confirm_clear_{tag_code}"):
                data[tag_code] = {"RFID Tag Code": tag_code, "_cleared": True,
                    "_cleared_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                save_data(data)
                st.session_state.pop(f"v_mode_{tag_code}", None)
                st.session_state.pop(f"auth_ok_{tag_code}", None)
                st.success("✅ Tag cleared.")
                st.rerun()
        with cc2:
            if st.button("✕  Cancel", use_container_width=True,
                         key=f"v_cancel_clear_{tag_code}"):
                st.session_state.pop(f"v_mode_{tag_code}", None)
                st.session_state.pop(f"auth_ok_{tag_code}", None)
                st.rerun()

    if mode == "edit":
        st.markdown("---")
        _show_edit_form(tag_code, rec, data, is_empty=False)

# ─────────────────────────────────────────────
# ADMIN CSS
# ─────────────────────────────────────────────
ADMIN_CSS = """
<style>
#MainMenu, footer {visibility: hidden;}
.stTabs [data-baseweb="tab-list"] {gap: 8px;}
.stTabs [data-baseweb="tab"] {padding: 6px 20px; border-radius: 6px; font-size: 0.82rem;}
.stTabs [aria-selected="true"] {background: #1a3a6b !important; color: #4f9cf9 !important;}
div[data-testid="stMetricValue"] {font-size: 1.8rem !important;}
.qr-card { background: #1a1d27; border: 1px solid #2e3347; border-radius: 10px; padding: 1rem; text-align: center; margin-bottom: 0.5rem; }
.bin-badge { background: rgba(79,156,249,0.15); color: #4f9cf9; padding: 2px 10px; border-radius: 20px; font-family: monospace; font-size: 0.78rem; font-weight: 700; display: inline-block; margin-bottom: 4px; word-break: break-all; }
.status-ok   { color: #34d399; font-size: 0.75rem; }
.status-empty { color: #7a8299; font-size: 0.75rem; }
</style>
"""

# ─────────────────────────────────────────────
# SETUP TAB
# ─────────────────────────────────────────────
def tab_setup():
    st.subheader("App Configuration")

    # ── App URL ───────────────────────────────────────────────
    st.markdown("### App URL (for QR codes)")
    st.success(f"**Active URL:** {get_base_url()}")
    st.caption("QR codes link to this URL with ?tag=RFID_TAG_CODE appended.")

    with st.expander("Change URL (optional)"):
        st.warning("Only change if you move the app to a different address.")
        url_input = st.text_input("New App URL", value=get_base_url(),
            placeholder="https://your-app-name.streamlit.app", key="setup_url_input")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Save new URL", type="primary", use_container_width=True, key="setup_save_url"):
                st.session_state["base_url"] = url_input.strip().rstrip("/")
                st.success(f"URL updated.")
                st.rerun()
        with c2:
            if st.button("Reset to default", use_container_width=True, key="setup_reset_url"):
                st.session_state.pop("base_url", None)
                st.success(f"Reset to default.")
                st.rerun()

    st.markdown("---")

    # ── Master Material List ──────────────────────────────────
    st.markdown("### 📋 Master Material List")
    st.caption("Upload once — the system uses this list for auto-fill in Register and Edit.")

    master_records = load_master()
    if master_records:
        master_df_cur = pd.DataFrame(master_records)
        st.success(f"✅ Master list loaded — **{len(master_df_cur)} materials**")
        with st.expander("Preview master list"):
            st.dataframe(master_df_cur, use_container_width=True, height=220)
        if st.button("🗑 Remove master list", type="secondary", key="del_master"):
            save_master([])
            st.success("Master list removed.")
            st.rerun()
    else:
        st.info("No master list uploaded yet.")

    master_upload = st.file_uploader(
        "Upload Master Material CSV", type=["csv"], key="setup_master_csv",
        help="CSV with material columns: Material, Material Description, Plant, Storage Bin, etc."
    )
    if master_upload:
        df_m, err_m = parse_csv_generic(master_upload)
        if err_m:
            st.error(f"CSV error: {err_m}")
        else:
            save_master(df_m.to_dict(orient="records"))
            st.success(f"✅ Master list saved — {len(df_m)} materials.")
            st.rerun()

    st.markdown("---")

    # ── Password ──────────────────────────────────────────────
    st.markdown("### 🔒 Warehouse Password")
    current_pw = get_password()
    st.info(f"Current password: **{'*' * len(current_pw)}** ({len(current_pw)} chars)  ·  Default: `RFID123`")

    with st.expander("Change Password (optional)"):
        ca, cb = st.columns(2)
        with ca:
            new_pw1 = st.text_input("New Password", type="password", key="new_pw1",
                                     placeholder="Enter new password")
        with cb:
            new_pw2 = st.text_input("Confirm Password", type="password", key="new_pw2",
                                     placeholder="Repeat new password")
        pc1, pc2 = st.columns(2)
        with pc1:
            if st.button("💾 Save Password", type="primary", use_container_width=True, key="setup_save_pw"):
                if not new_pw1:
                    st.error("Password cannot be empty.")
                elif new_pw1 != new_pw2:
                    st.error("Passwords do not match.")
                elif len(new_pw1) < 4:
                    st.error("Minimum 4 characters.")
                else:
                    st.session_state["app_password"] = new_pw1
                    st.success("✅ Password updated.")
        with pc2:
            if st.button("↩ Reset to RFID123", use_container_width=True, key="setup_reset_pw"):
                st.session_state.pop("app_password", None)
                st.success("Reset to RFID123")
                st.rerun()

    st.markdown("---")
    st.markdown("### Database status")
    data = load_data()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total tags", len(data))
    c2.metric("Active tags", sum(1 for v in data.values() if not v.get("_cleared") and v.get("Material")))
    c3.metric("Empty tags",  sum(1 for v in data.values() if v.get("_cleared") or not v.get("Material")))
    if data:
        st.markdown("---")
        if st.button("🗑 Reset ALL tag data", type="secondary", key="setup_reset_all"):
            save_data({})
            st.success("All tag data cleared.")
            st.rerun()

# ─────────────────────────────────────────────
# REGISTER TAB
# ─────────────────────────────────────────────
def tab_register():
    st.subheader("📋 Register Material to RFID Tag")

    reg_mode = st.radio(
        "Registration method",
        ["🗂 Quick: Select from Master List", "📄 Bulk: Upload CSV file"],
        horizontal=True, key="reg_mode"
    )
    st.markdown("---")

    # ════════════════════════════════════════════════════════
    # QUICK MODE
    # ════════════════════════════════════════════════════════
    if reg_mode == "🗂 Quick: Select from Master List":

        master_df = get_master_df()
        if master_df is None:
            st.warning("⚠️ No Master Material List found.")
            st.info("Go to **Setup tab → Master Material List** and upload your CSV first.")
            return

        st.success(f"✅ Using master list — {len(master_df)} materials available")

        # ── RFID Tag input ────────────────────────────────────
        st.markdown("### Step 1 — RFID Tag Code")
        tag_file = st.file_uploader(
            "Upload RFID Tag List CSV (optional)", type=["csv"], key="tag_list_csv",
            help="CSV with RFID Tag Code column — enables dropdown tag selection"
        )
        tag_options = []
        if tag_file:
            df_t, err_t = parse_csv_generic(tag_file)
            if not err_t and "RFID Tag Code" in df_t.columns:
                tag_options = df_t["RFID Tag Code"].str.strip().dropna().unique().tolist()
                st.success(f"✅ {len(tag_options)} tags loaded")

        if tag_options:
            inp_mode = st.radio("Tag input", ["Select from list", "Type manually"],
                                horizontal=True, key="tag_input_mode")
            if inp_mode == "Select from list":
                sel_tag = st.selectbox("Select RFID Tag",
                    options=["— choose tag —"] + tag_options, key="tag_select")
                tag_code = "" if sel_tag == "— choose tag —" else sel_tag
            else:
                tag_code = st.text_input("Type RFID Tag Code",
                    placeholder="E2801191A504...", key="tag_manual_input").strip()
        else:
            tag_code = st.text_input("Type RFID Tag Code",
                placeholder="E2801191A504...", key="tag_manual_input2").strip()

        # ── Material selector ─────────────────────────────────
        st.markdown("### Step 2 — Select Material")
        disp = master_display_opts(master_df)
        selected_mat = st.selectbox("Material from master list",
            options=disp, key="master_mat_select")

        if not tag_code:
            st.warning("⚠️ Enter an RFID Tag Code above.")

        st.markdown("---")
        st.markdown("### Step 3 — Fill in material information")

        rmode_key   = "rq_mode"
        rloaded_key = "rq_loaded"
        rform_key   = "rq_form"
        rfirst_key  = "rq_first"

        def _rcleanup():
            for field in EXPECTED_COLS:
                if field == "RFID Tag Code": continue
                for sfx in ["_sel","_custom","_txt"]:
                    st.session_state.pop(f"rwk_{field}{sfx}", None)
            for k in [rmode_key, rloaded_key, rform_key, rfirst_key,
                      "rq_search","rq_chosen"]:
                st.session_state.pop(k, None)

        # ── Step 3a: Choose mode ──────────────────────────────
        if rmode_key not in st.session_state:
            rc1, rc2 = st.columns(2)
            with rc1:
                md = master_df is None
                if st.button("📋 From Master Database",
                             use_container_width=True, type="primary",
                             disabled=md, key="rq_btn_master"):
                    st.session_state[rmode_key] = "master"
                    st.rerun()
            with rc2:
                if st.button("✏️ Fill Manually",
                             use_container_width=True, key="rq_btn_manual"):
                    st.session_state[rmode_key]   = "manual"
                    st.session_state[rloaded_key] = {f:"" for f in EXPECTED_COLS}
                    st.session_state[rform_key]   = True
                    st.rerun()

        elif st.session_state[rmode_key] == "master" and not st.session_state.get(rform_key):
            # ── Step 3b: Search ───────────────────────────────
            st.markdown("**Search material from Master Database**")
            rq = st.text_input("Search", placeholder="Material ID, description...",
                key="rq_search")
            if rq.strip():
                rmask = master_df.apply(
                    lambda row: any(rq.lower() in str(v).lower() for v in row.values), axis=1)
                rfiltered = master_df[rmask]
            else:
                rfiltered = master_df
            st.caption(f"{len(rfiltered)} results")

            if len(rfiltered) > 0:
                rmc  = next((c for c in rfiltered.columns if "Material Description" in c), None)
                rmic = next((c for c in rfiltered.columns if c.strip() == "Material"), None)
                if rmic and rmc:
                    ropts = ["— select —"] + [f"{r[rmic]}  |  {r[rmc]}" for _,r in rfiltered.iterrows()]
                elif rmic:
                    ropts = ["— select —"] + rfiltered[rmic].tolist()
                else:
                    ropts = ["— select —"] + [f"Row {i+1}" for i in range(len(rfiltered))]

                rchosen = st.selectbox("Material", ropts, key="rq_chosen",
                    label_visibility="collapsed")
                rl1, rl2 = st.columns([2,1])
                with rl1:
                    if st.button("✅ Load into form", use_container_width=True,
                                 type="primary", key="rq_load",
                                 disabled=(rchosen=="— select —")):
                        ridx = ropts.index(rchosen) - 1
                        rrow = rfiltered.iloc[ridx]
                        rl = {f: str(rrow.get(f,"")).strip()
                              for f in EXPECTED_COLS if f in rfiltered.columns}
                        st.session_state[rloaded_key] = rl
                        st.session_state[rform_key]   = True
                        st.rerun()
                with rl2:
                    if st.button("← Back", use_container_width=True, key="rq_back"):
                        st.session_state.pop(rmode_key, None)
                        st.rerun()
            else:
                st.warning("No results.")

        else:
            # ── Step 3c: Edit form ────────────────────────────
            rloaded = st.session_state.get(rloaded_key, {f:"" for f in EXPECTED_COLS})
            rmode   = st.session_state.get(rmode_key, "manual")

            if rmode == "master":
                rn = rloaded.get("Material Description", rloaded.get("Material",""))
                st.success(f"📋 Loaded: **{rn}**")

            if not tag_code:
                st.warning("⚠️ Enter RFID Tag Code in Step 2 above.")

            st.markdown(f"**RFID Tag Code:** `{tag_code or '(not set)'}`")
            st.markdown("---")

            if rfirst_key not in st.session_state:
                for field in EXPECTED_COLS:
                    if field == "RFID Tag Code": continue
                    for sfx in ["_sel","_custom","_txt"]:
                        st.session_state.pop(f"rwk_{field}{sfx}", None)
                st.session_state[rfirst_key] = True

            rca, rcb = st.columns(2)
            for j, field in enumerate(EXPECTED_COLS):
                if field == "RFID Tag Code": continue
                rwk = f"rwk_{field}"
                rv  = rloaded.get(field,"")
                target = rca if j % 2 == 0 else rcb
                with target:
                    if field in DROPDOWN_FIELDS:
                        db2 = load_data()
                        ropts2 = get_field_options(db2, field)
                        if field in master_df.columns:
                            for v in master_df[field].dropna().unique():
                                if str(v).strip(): ropts2 = sorted(set(ropts2)|{str(v).strip()})
                        if rv and rv not in ropts2:
                            ropts2 = sorted(ropts2 + [rv])
                        CUSTOM = "— type custom value —"
                        rch = ropts2 + [CUSTOM]
                        ridx2 = ropts2.index(rv) if rv in ropts2 else len(rch)-1
                        rsel = st.selectbox(field, rch, index=ridx2, key=f"{rwk}_sel")
                        if rsel == CUSTOM:
                            st.text_input(f"Custom {field}", value=rv,
                                key=f"{rwk}_custom", placeholder=f"Enter {field}...")
                    else:
                        st.text_input(field, value=rv, key=f"{rwk}_txt")

            st.markdown("---")
            rs1, rs2, rs3 = st.columns([2,2,1])
            with rs1:
                rsave = st.button("💾 Save to Tag", type="primary",
                    use_container_width=True, key="rq_save")
            with rs2:
                if rmode == "master":
                    if st.button("🔍 Change material", use_container_width=True,
                                 key="rq_change"):
                        st.session_state.pop(rloaded_key, None)
                        st.session_state.pop(rform_key, None)
                        st.session_state.pop(rfirst_key, None)
                        st.rerun()
            with rs3:
                rcancel = st.button("✕", use_container_width=True, key="rq_cancel")

            if rsave:
                if not tag_code:
                    st.error("⚠️ Enter RFID Tag Code first.")
                else:
                    db3 = load_data()
                    new_vals = {"RFID Tag Code": tag_code}
                    for field in EXPECTED_COLS:
                        if field == "RFID Tag Code": continue
                        rwk = f"rwk_{field}"
                        if field in DROPDOWN_FIELDS:
                            sv = st.session_state.get(f"{rwk}_sel","")
                            new_vals[field] = (st.session_state.get(f"{rwk}_custom","")
                                if sv == "— type custom value —" else sv)
                        else:
                            new_vals[field] = st.session_state.get(f"{rwk}_txt","")
                    new_vals["_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    db3[tag_code] = new_vals
                    save_data(db3)
                    _rcleanup()
                    st.success(f"✅ Tag **{tag_code}** registered!")
                    st.balloons()

            if rcancel:
                _rcleanup()
                st.rerun()


    # ════════════════════════════════════════════════════════
    # BULK MODE
    # ════════════════════════════════════════════════════════
    else:
        st.info("Upload a CSV with both **RFID Tag Code** and material columns filled.")
        uploaded = st.file_uploader("Upload CSV file", type=["csv"], key="reg_csv")

        if not uploaded:
            st.markdown("""
**Required columns:**
`Material` · `Plant` · `Storage Location` · `Storage Type` · `Storage Section` ·
`Storage Bin` · `Material Description` · `Batch` · `Stock Category` ·
`Total Stock` · `Base Unit of Measure` · `SLED/BBD` · `GR Date` · **`RFID Tag Code`**
""")
            return

        df, err = parse_csv(uploaded)
        if err:
            st.error(f"CSV error: {err}")
            return

        st.success(f"✅ Loaded {len(df)} rows")
        st.dataframe(df, use_container_width=True, height=250)
        st.markdown("---")
        _, col2 = st.columns([3, 1])
        with col2:
            overwrite = st.checkbox("Overwrite existing", value=True, key="reg_overwrite")

        if st.button("☁ Register All", type="primary", use_container_width=True, key="reg_submit"):
            data = load_data()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            skipped = registered = 0
            prog = st.progress(0, text="Registering...")
            for i, row in df.iterrows():
                tc = str(row.get("RFID Tag Code","")).strip()
                if not tc:
                    skipped += 1; continue
                if tc in data and not overwrite:
                    skipped += 1; continue
                rec = {col: str(row.get(col,"")).strip()
                       for col in EXPECTED_COLS if col in df.columns}
                rec["RFID Tag Code"] = tc
                rec["_updated_at"]   = now
                data[tc] = rec
                registered += 1
                prog.progress((i+1)/len(df), text=f"Registering {tc[:16]}...")
            save_data(data)
            prog.empty()
            st.success(f"✅ {registered} registered · {skipped} skipped")
            st.balloons()

# ─────────────────────────────────────────────
# QR CODES TAB
# ─────────────────────────────────────────────
def tab_qrcodes():
    st.subheader("◻ QR Code Gallery")
    data = load_data()
    if not data:
        st.warning("No tags registered yet.")
        return

    c1, c2 = st.columns([4,1])
    with c1:
        search = st.text_input("Search", placeholder="Filter by tag, bin, material...",
            label_visibility="collapsed", key="qr_search")
    with c2:
        dl_all = st.button("⬇ Download All", use_container_width=True, key="qr_dl_all")

    tags = {k: v for k,v in data.items()
            if search.lower() in k.lower()
            or search.lower() in v.get("Material","").lower()
            or search.lower() in v.get("Storage Bin","").lower()
            or search.lower() in v.get("Material Description","").lower()}

    st.caption(f"Showing {len(tags)} of {len(data)} tags")

    if dl_all:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf,"w") as zf:
            for tc, rec in data.items():
                bid = rec.get("Storage Bin", tc[:8])
                img = make_qr_image(tag_url(tc), f"Bin:{bid}", tc[:16])
                zf.writestr(f"QR_{bid}_{tc[:8]}.png", qr_to_bytes(img))
        zip_buf.seek(0)
        st.download_button("📦 Download ZIP", data=zip_buf,
            file_name="RFID_QR_Codes.zip", mime="application/zip")

    cols = st.columns(4)
    for i, (tc, rec) in enumerate(tags.items()):
        has_data = bool(rec.get("Material")) and not rec.get("_cleared")
        bid  = rec.get("Storage Bin","—")
        img  = make_qr_image(tag_url(tc), f"Bin: {bid}", tc[:20])
        with cols[i%4]:
            st.markdown('<div class="qr-card">', unsafe_allow_html=True)
            st.markdown(f'<div class="bin-badge">Bin: {bid}</div>', unsafe_allow_html=True)
            st.markdown(f'<div style="font-size:0.62rem;color:#5a6280;font-family:monospace;margin-bottom:4px;word-break:break-all;">{tc}</div>', unsafe_allow_html=True)
            st.image(img, use_container_width=True)
            if has_data:
                st.markdown(f'<div class="status-ok">● {rec.get("Material","")[:18]}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="status-empty">○ Empty</div>', unsafe_allow_html=True)
            st.download_button("⬇ PNG", data=qr_to_bytes(img),
                file_name=f"QR_{bid}_{tc[:8]}.png", mime="image/png",
                key=f"dl_{tc}", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# MANAGE TAB
# ─────────────────────────────────────────────
def tab_manage():
    st.subheader("🗂 Material Tag Manager")
    data = load_data()
    if not data:
        st.warning("No tags registered yet.")
        return

    search = st.text_input("Search", placeholder="Filter by tag, bin, material...",
        label_visibility="collapsed", key="manage_search")
    tags = {k: v for k,v in data.items()
            if search.lower() in k.lower()
            or search.lower() in v.get("Material","").lower()
            or search.lower() in v.get("Storage Bin","").lower()
            or search.lower() in v.get("Material Description","").lower()}

    st.caption(f"{len(tags)} tags shown")

    for tc, rec in tags.items():
        has_data     = bool(rec.get("Material")) and not rec.get("_cleared")
        status_color = "#34d399" if has_data else "#7a8299"
        status_txt   = "Active" if has_data else "Empty"
        bid          = rec.get("Storage Bin","—")
        mat_desc     = rec.get("Material Description","(empty)")[:50]

        with st.expander(f"{'●' if has_data else '○'} **Bin {bid}** · {mat_desc}"):
            st.markdown(f"""
            <div style="background:#0d1a2e;border:1px solid #2a4a7a;border-radius:8px;
                padding:0.6rem 1rem;margin-bottom:0.75rem;">
              <div style="font-size:0.68rem;color:#5a7299;text-transform:uppercase;letter-spacing:1px;">RFID Tag Code (permanent)</div>
              <div style="font-family:monospace;font-size:0.88rem;color:#7ab8f5;word-break:break-all;margin-top:2px;">{tc}</div>
            </div>""", unsafe_allow_html=True)

            c1, c2 = st.columns([3,1])
            with c1:
                st.markdown(f"**Status:** <span style='color:{status_color}'>{status_txt}</span>",
                    unsafe_allow_html=True)
                if has_data:
                    st.markdown(f"**Material:** `{rec.get('Material','—')}`")
                    st.markdown(f"**Stock:** {rec.get('Total Stock','—')} {rec.get('Base Unit of Measure','')}")
                    st.markdown(f"**Batch:** {rec.get('Batch','—')}")
                    st.markdown(f"**GR Date:** {rec.get('GR Date','—')}")
                    st.markdown(f"**SLED/BBD:** {rec.get('SLED/BBD','—')}")
            with c2:
                st.markdown(f"[🔗 View]({tag_url(tc)})")

            st.markdown("---")
            ac = st.columns(3)
            with ac[0]:
                if st.button("✎ Edit", key=f"edit_{tc}", use_container_width=True):
                    st.session_state[f"editing_{tc}"] = True
            with ac[1]:
                if st.button("✕ Clear", key=f"clear_{tc}",
                             use_container_width=True, type="secondary"):
                    data[tc] = {"RFID Tag Code": tc, "_cleared": True,
                        "_cleared_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                    save_data(data)
                    st.success("Tag cleared.")
                    st.rerun()
            with ac[2]:
                qr_img = make_qr_image(tag_url(tc), f"Bin: {bid}", tc[:20])
                st.download_button("⬇ QR", data=qr_to_bytes(qr_img),
                    file_name=f"QR_{bid}_{tc[:8]}.png", mime="image/png",
                    key=f"qrdl_{tc}", use_container_width=True)

            # ── Edit form with master list ────────────────────
            if st.session_state.get(f"editing_{tc}"):
                st.markdown("---")
                st.markdown("#### ✎ Edit material data")

                mmode_key   = f"mm_mode_{tc}"
                mloaded_key = f"mm_loaded_{tc}"
                mform_key   = f"mm_form_{tc}"
                mfirst_key  = f"mm_first_{tc}"
                master_df   = get_master_df()

                def _mcleanup():
                    for field in EXPECTED_COLS:
                        if field == "RFID Tag Code": continue
                        for sfx in ["_sel","_custom","_txt"]:
                            st.session_state.pop(f"mwk_{tc}_{field}{sfx}", None)
                    for k in [mmode_key, mloaded_key, mform_key, mfirst_key]:
                        st.session_state.pop(k, None)
                    st.session_state[f"editing_{tc}"] = False

                # ── Step 1: Choose mode ───────────────────────
                if mmode_key not in st.session_state:
                    st.markdown("**How would you like to fill in the information?**")
                    mc1, mc2 = st.columns(2)
                    with mc1:
                        md = master_df is None
                        if st.button("📋 From Master Database",
                                     use_container_width=True, type="primary",
                                     disabled=md, key=f"mm_btn_master_{tc}"):
                            st.session_state[mmode_key] = "master"
                            st.rerun()
                        if md: st.caption("Upload Master CSV in Setup first")
                    with mc2:
                        if st.button("✏️ Fill Manually",
                                     use_container_width=True, key=f"mm_btn_manual_{tc}"):
                            st.session_state[mmode_key]   = "manual"
                            st.session_state[mloaded_key] = {f: rec.get(f,"") for f in EXPECTED_COLS}
                            st.session_state[mform_key]   = True
                            st.rerun()
                    if st.button("✕ Cancel edit", key=f"mm_cancel_mode_{tc}"):
                        st.session_state[f"editing_{tc}"] = False
                        st.rerun()

                elif st.session_state[mmode_key] == "master" and not st.session_state.get(mform_key):
                    # ── Step 2: Search ────────────────────────
                    st.markdown("**Search & select material**")
                    mq = st.text_input("Search material",
                        placeholder="Material ID, description...",
                        key=f"mm_search_{tc}")
                    if mq.strip():
                        mask = master_df.apply(
                            lambda row: any(mq.lower() in str(v).lower() for v in row.values), axis=1)
                        mfiltered = master_df[mask]
                    else:
                        mfiltered = master_df
                    st.caption(f"{len(mfiltered)} results")

                    if len(mfiltered) > 0:
                        mc = next((c for c in mfiltered.columns if "Material Description" in c), None)
                        mic = next((c for c in mfiltered.columns if c.strip() == "Material"), None)
                        if mic and mc:
                            mopts = ["— select —"] + [f"{r[mic]}  |  {r[mc]}" for _,r in mfiltered.iterrows()]
                        elif mic:
                            mopts = ["— select —"] + mfiltered[mic].tolist()
                        else:
                            mopts = ["— select —"] + [f"Row {i+1}" for i in range(len(mfiltered))]

                        mchosen = st.selectbox("Material", options=mopts,
                            key=f"mm_chosen_{tc}", label_visibility="collapsed")
                        ml1, ml2 = st.columns([2,1])
                        with ml1:
                            if st.button("✅ Load into form", use_container_width=True,
                                         type="primary", key=f"mm_load_{tc}",
                                         disabled=(mchosen=="— select —")):
                                midx = mopts.index(mchosen) - 1
                                mrow = mfiltered.iloc[midx]
                                ml = {f: str(mrow.get(f,"")).strip()
                                      for f in EXPECTED_COLS if f in mfiltered.columns}
                                ml["RFID Tag Code"] = tc
                                st.session_state[mloaded_key] = ml
                                st.session_state[mform_key]   = True
                                st.rerun()
                        with ml2:
                            if st.button("← Back", use_container_width=True,
                                         key=f"mm_back_{tc}"):
                                st.session_state.pop(mmode_key, None)
                                st.rerun()
                    else:
                        st.warning("No results.")
                        if st.button("← Back", key=f"mm_back2_{tc}"):
                            st.session_state.pop(mmode_key, None)
                            st.rerun()

                else:
                    # ── Step 3: Edit form ─────────────────────
                    mloaded = st.session_state.get(mloaded_key,
                        {f: rec.get(f,"") for f in EXPECTED_COLS})
                    mmode = st.session_state[mmode_key]
                    if mmode == "master":
                        mn = mloaded.get("Material Description", mloaded.get("Material",""))
                        st.success(f"📋 Loaded: **{mn}**")

                    st.markdown(f"**RFID Tag Code (fixed):** `{tc}`")
                    st.markdown("---")

                    if mfirst_key not in st.session_state:
                        for field in EXPECTED_COLS:
                            if field == "RFID Tag Code": continue
                            for sfx in ["_sel","_custom","_txt"]:
                                st.session_state.pop(f"mwk_{tc}_{field}{sfx}", None)
                        st.session_state[mfirst_key] = True

                    mca, mcb = st.columns(2)
                    for j, field in enumerate(EXPECTED_COLS):
                        if field == "RFID Tag Code": continue
                        mwk = f"mwk_{tc}_{field}"
                        mv  = mloaded.get(field,"")
                        tgt = mca if j % 2 == 0 else mcb
                        with tgt:
                            if field in DROPDOWN_FIELDS:
                                mopts2 = get_field_options(data, field)
                                if mv and mv not in mopts2:
                                    mopts2 = sorted(mopts2 + [mv])
                                CUSTOM = "— type custom value —"
                                mch = mopts2 + [CUSTOM]
                                midx2 = mopts2.index(mv) if mv in mopts2 else len(mch)-1
                                msel = st.selectbox(field, mch, index=midx2, key=f"{mwk}_sel")
                                if msel == CUSTOM:
                                    st.text_input(f"Custom {field}", value=mv,
                                        key=f"{mwk}_custom", placeholder=f"Enter {field}...")
                            else:
                                st.text_input(field, value=mv, key=f"{mwk}_txt")

                    st.markdown("---")
                    ms1, ms2, ms3 = st.columns([2,2,1])
                    with ms1:
                        msave = st.button("💾 Save Changes", type="primary",
                            use_container_width=True, key=f"mm_save_{tc}")
                    with ms2:
                        if mmode == "master":
                            if st.button("🔍 Change material", use_container_width=True,
                                         key=f"mm_change_{tc}"):
                                st.session_state.pop(mloaded_key, None)
                                st.session_state.pop(mform_key, None)
                                st.session_state.pop(mfirst_key, None)
                                st.rerun()
                    with ms3:
                        mcancel = st.button("✕", use_container_width=True,
                            key=f"mm_cancel_{tc}")

                    if msave:
                        new_vals = {"RFID Tag Code": tc}
                        for field in EXPECTED_COLS:
                            if field == "RFID Tag Code": continue
                            mwk = f"mwk_{tc}_{field}"
                            if field in DROPDOWN_FIELDS:
                                sv = st.session_state.get(f"{mwk}_sel","")
                                new_vals[field] = (st.session_state.get(f"{mwk}_custom","")
                                    if sv == "— type custom value —" else sv)
                            else:
                                new_vals[field] = st.session_state.get(f"{mwk}_txt","")
                        new_vals["_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        data[tc] = new_vals
                        save_data(data)
                        _mcleanup()
                        st.success("✅ Tag updated!")
                        st.rerun()

                    if mcancel:
                        _mcleanup()
                        st.rerun()


def main():
    try:
        tag_param = st.query_params.get("tag", None)
        if tag_param:
            tag_param = str(tag_param).strip()
    except Exception:
        tag_param = None

    if tag_param:
        show_viewer(tag_param)
        return

    st.markdown(ADMIN_CSS, unsafe_allow_html=True)
    st.markdown("""
    <div style="background:linear-gradient(135deg,#0d1b3e,#1a1040);
        padding:1rem 1.5rem;border-radius:10px;margin-bottom:1rem;">
      <div style="font-family:monospace;color:#4f9cf9;font-size:1rem;
          letter-spacing:2px;font-weight:700;">
          RFID<span style="color:#7c5cbf">·QR</span> MANAGER</div>
      <div style="font-size:0.72rem;color:#7a8299;margin-top:2px;letter-spacing:1px;">
          MATERIAL TRACKING SYSTEM</div>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["⚙ Setup", "📋 Register", "◻ QR Codes", "🗂 Manage"])
    with tab1: tab_setup()
    with tab2: tab_register()
    with tab3: tab_qrcodes()
    with tab4: tab_manage()

if __name__ == "__main__":
    main()
