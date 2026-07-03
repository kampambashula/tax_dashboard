"""
Zambia MTRS Executive Dashboard
Ministry of Finance / Zambia Revenue Authority
--------------------------------------------------------------
Reads the statistical bulletin workbook (data/data.xls), cleans it,
classifies every column into a logical revenue-administration section,
and renders an executive-level, interactive Streamlit dashboard.

The column classification is driven by a positional section map that
mirrors the structure of the ZRA/MOF statistical bulletin (revenue,
% of GDP, taxpayer segments, administration, VAT refunds, trade summary,
commodity sections, trading partners, border posts). If a future edition
of the bulletin keeps the same table order, the app will classify it
automatically without any code changes.
"""

import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ============================================================================
# PAGE CONFIG & THEME
# ============================================================================

st.set_page_config(
    page_title="Zambia MTRS Executive Dashboard",
    page_icon="🇿🇲",
    layout="wide",
    initial_sidebar_state="expanded",
)

PRIMARY = "#0B5D3B"      # deep green
SECONDARY = "#C8A84B"    # gold
ACCENT = "#8C1D18"       # deep red
INK = "#1B1F1D"
PALETTE = ["#0B5D3B", "#C8A84B", "#8C1D18", "#2C6E8C", "#5B4B8A",
           "#B0763A", "#3E7C5B", "#7A7A7A", "#94572B", "#3D5A80"]

CUSTOM_CSS = f"""
<style>
    .stApp {{ background-color: #F6F7F5; }}
    section[data-testid="stSidebar"] {{
        background-color: {INK};
    }}
    section[data-testid="stSidebar"] * {{ color: #EDEDED !important; }}
    div[data-testid="stMetric"] {{
        background: #FFFFFF;
        border: 1px solid #E4E4E0;
        border-left: 5px solid {PRIMARY};
        border-radius: 8px;
        padding: 14px 16px 10px 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }}
    div[data-testid="stMetricLabel"] {{ color: #4A4A4A; font-weight: 600; }}
    div[data-testid="stMetricValue"] {{ color: {PRIMARY}; }}
    .section-header {{
        background: linear-gradient(90deg, {PRIMARY} 0%, #0f7a4d 100%);
        color: white;
        padding: 10px 18px;
        border-radius: 8px;
        margin: 18px 0 10px 0;
        font-size: 1.05rem;
        font-weight: 700;
        letter-spacing: 0.02em;
    }}
    .insight-box {{
        background: #FFF9EC;
        border-left: 4px solid {SECONDARY};
        padding: 10px 16px;
        border-radius: 6px;
        font-size: 0.92rem;
        color: #3A3A3A;
        margin-bottom: 18px;
    }}
    .top-banner {{
        background: linear-gradient(90deg, {INK} 0%, {PRIMARY} 100%);
        padding: 22px 28px;
        border-radius: 10px;
        color: white;
        margin-bottom: 6px;
    }}
    div[data-testid="stTabs"] button {{ font-weight: 600; }}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

DATA_PATH = Path(__file__).parent / "data" / "data.xls"

# ============================================================================
# SECTION MAP (positional classification of the bulletin's column blocks)
# ============================================================================
# (start_idx, end_idx_inclusive, section_key, section_title, unit)
SECTION_MAP = [
    (1, 19, "revenue_nominal", "Revenue Performance", "ZMW million"),
    (20, 30, "revenue_gdp", "Revenue as % of GDP", "% of GDP"),
    (31, 34, "taxpayer_segments", "Taxpayer Segment Contribution", "ZMW million"),
    (35, 38, "admin_cost", "Revenue Administration & Collection Efficiency", "mixed"),
    (39, 45, "vat_refunds", "VAT Refunds", "ZMW million"),
    (46, 53, "trade_summary", "Customs & Trade Summary", "mixed"),
    (54, 75, "imports_hs", "Imports by Commodity Section", "ZMW million"),
    (76, 97, "exports_hs", "Exports by Commodity Section", "ZMW million"),
    (98, 109, "partners_imports", "Imports by Trading Partner", "ZMW million"),
    (110, 121, "partners_exports", "Exports by Trading Partner", "ZMW million"),
    (122, 132, "export_port_exit", "Export Value by Border Post (Exit)", "ZMW million"),
    (133, 143, "import_port_exit", "Import Value by Border Post (Entry)", "ZMW million"),
    (144, 154, "value_imports_port", "Value of Imports by Border Post", "ZMW million"),
    (155, 165, "rexports_port", "Re-exports by Border Post", "ZMW million"),
    (166, 176, "reimports_port", "Re-imports by Border Post", "ZMW million"),
]

PERCENT_COLS_CLEAN = set()   # filled during classification
COUNT_COLS_CLEAN = set()     # filled during classification


def short_label(name: str, max_len: int = 34) -> str:
    """Shorten long HS-style descriptions for chart axis labels."""
    base = name.split(";")[0].strip()
    if len(base) > max_len:
        base = base[: max_len - 1].rstrip() + "…"
    return base


def clean_header(raw: str) -> str:
    txt = raw.replace("\xa0", " ").strip()
    txt = re.sub(r"\s+", " ", txt)
    txt = re.sub(r"\[\d+\]", "", txt).strip()
    return txt


# ============================================================================
# DATA LOADING & CLEANING
# ============================================================================

@st.cache_data(show_spinner=False)
def load_and_classify(path: str):
    raw = pd.read_csv(path, sep="\t", encoding="iso-8859-1")
    raw_cols = list(raw.columns)

    meta = {}          # clean_name -> dict(section_key, section_title, unit, raw)
    rename_map = {}
    seen_clean = {}

    for idx, raw_name in enumerate(raw_cols):
        clean = clean_header(raw_name)
        if idx == 20:
            clean = "Tax Revenue (% of GDP)"
        elif idx == 47:
            clean = "No. of Import Entries"
        elif idx == 50:
            clean = "No. of Export Entries"

        # de-duplicate names that collide across different table blocks
        if clean in seen_clean:
            section_for_this = None
            for start, end, key, title, unit in SECTION_MAP:
                if start <= idx <= end:
                    section_for_this = title
                    break
            clean = f"{clean} ({section_for_this})" if section_for_this else f"{clean} ({idx})"
        seen_clean[clean] = idx
        rename_map[raw_name] = clean

        section_key, section_title, unit = "core", "Core", ""
        for start, end, key, title, u in SECTION_MAP:
            if start <= idx <= end:
                section_key, section_title, unit = key, title, u
                break
        meta[clean] = {
            "section_key": section_key if idx != 0 else "core",
            "section_title": section_title if idx != 0 else "Core",
            "unit": unit,
            "raw": raw_name,
            "index": idx,
        }

    df = raw.rename(columns=rename_map).copy()

    # --- cleaning ---
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    df.columns = [c.strip() if isinstance(c, str) else c for c in df.columns]

    for col in df.columns:
        if col == "Year":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
            continue
        # Normalize every non-Year column to numeric regardless of the dtype
        # pandas inferred on read (covers both legacy object and the newer
        # pandas string dtype, plus already-numeric columns).
        cleaned = (
            df[col].astype(str).str.strip()
            .replace({"-": None, "": None, "n/a": None, "N/A": None, "..": None, "nan": None, "<NA>": None}) # type: ignore
        )
        cleaned = cleaned.astype(str).str.replace(",", "", regex=False)
        df[col] = pd.to_numeric(cleaned, errors="coerce")

    df = df.dropna(subset=["Year"]).sort_values("Year").reset_index(drop=True)
    df["Year"] = df["Year"].astype(int)

    # classify percent / count columns for display formatting
    percent_cols = set()
    count_cols = set()
    for clean, m in meta.items():
        if clean not in df.columns:
            continue
        low = clean.lower()
        if m["section_key"] == "revenue_gdp":
            percent_cols.add(clean)
        elif "cost of collection" in low or "e-payment" in low or "cash or rtgs" in low:
            percent_cols.add(clean)
        elif "no. of" in low:
            count_cols.add(clean)

    return df, meta, percent_cols, count_cols


def fmt_kwacha(value_million: float) -> str:
    if pd.isna(value_million):
        return "n/a"
    if abs(value_million) >= 1000:
        return f"K{value_million/1000:,.1f} bn"
    return f"K{value_million:,.1f} m"


def fmt_pct(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value*100:,.1f}%"


def yoy(series: pd.Series):
    s = series.dropna()
    if len(s) < 2:
        return None
    prev, latest = s.iloc[-2], s.iloc[-1]
    if prev == 0 or pd.isna(prev):
        return None
    return (latest - prev) / prev


def cagr(series: pd.Series, years: pd.Series):
    s = series.dropna()
    if len(s) < 2 or s.iloc[0] <= 0:
        return None
    n = years.loc[s.index[-1]] - years.loc[s.index[0]]
    if n <= 0:
        return None
    return (s.iloc[-1] / s.iloc[0]) ** (1 / n) - 1


def trend_insight(df, col, label, unit="ZMW million", is_pct=False):
    s = df[[col, "Year"]].dropna()
    if s.empty:
        return f"No data reported for {label}."
    y0, y1 = int(s["Year"].iloc[0]), int(s["Year"].iloc[-1])
    v0, v1 = s[col].iloc[0], s[col].iloc[-1]
    peak_row = s.loc[s[col].idxmax()]
    trough_row = s.loc[s[col].idxmin()]
    change = yoy(s.set_index("Year")[col])
    if is_pct:
        val_fmt = lambda v: f"{v*100:.1f}%"
    elif unit == "ZMW million":
        val_fmt = fmt_kwacha
    else:
        val_fmt = lambda v: f"{v:,.0f}"

    direction = "risen" if v1 >= v0 else "declined"
    txt = (
        f"{label} {direction} from {val_fmt(v0)} in {y0} to {val_fmt(v1)} in {y1}"
        f", peaking at {val_fmt(peak_row[col])} in {int(peak_row['Year'])}."
    )
    if change is not None:
        chg_dir = "grew" if change >= 0 else "contracted"
        txt += f" It {chg_dir} {abs(change)*100:.1f}% in the latest year on year."
    return txt


def ranking_insight(series: pd.Series, label: str, unit_fmt=fmt_kwacha, year=None):
    s = series.dropna().sort_values(ascending=False)
    if s.empty:
        return f"No data reported for {label}."
    total = s.sum()
    top = s.index[0]
    top_val = s.iloc[0]
    top_share = top_val / total if total else 0
    txt = f"{top} led {label.lower()}"
    if year is not None:
        txt += f" in {year}"
    txt += f" at {unit_fmt(top_val)}, a {top_share*100:.1f}% share of the total."
    if len(s) > 1:
        second = s.index[1]
        txt += f" {second} followed at {unit_fmt(s.iloc[1])}."
    return txt


def section_header(title: str, icon: str = "📊"):
    st.markdown(f'<div class="section-header">{icon}  {title}</div>', unsafe_allow_html=True)


def insight_box(text: str):
    st.markdown(f'<div class="insight-box">💡 {text}</div>', unsafe_allow_html=True)


def cols_in_section(meta, section_key, df_columns):
    return [c for c, m in meta.items() if m["section_key"] == section_key and c in df_columns]


# ============================================================================
# LOAD DATA
# ============================================================================

if not DATA_PATH.exists():
    st.error(f"Data file not found at {DATA_PATH}. Please confirm the upload path.")
    st.stop()

df, META, PCT_COLS, COUNT_COLS = load_and_classify(str(DATA_PATH))

# drop columns that are entirely zero/constant everywhere from active charting
CONST_COLS = [c for c in df.columns if c != "Year" and df[c].nunique(dropna=True) <= 1]

YEARS = sorted(df["Year"].unique().tolist())

# ============================================================================
# SIDEBAR — FILTERS
# ============================================================================

st.sidebar.markdown("## 🇿🇲 MTRS Dashboard")
st.sidebar.caption("Ministry of Finance & National Planning · Zambia Revenue Authority")
st.sidebar.markdown("---")

year_range = st.sidebar.select_slider(
    "Year range",
    options=YEARS,
    value=(YEARS[0], YEARS[-1]),
)
sel_years = [y for y in YEARS if year_range[0] <= y <= year_range[1]]
fdf = df[df["Year"].isin(sel_years)].reset_index(drop=True)

top_n = st.sidebar.slider("Top-N items in ranking charts", min_value=3, max_value=15, value=8)

search_term = st.sidebar.text_input("Search commodity / partner / border post", "")

st.sidebar.markdown("---")
st.sidebar.download_button(
    "⬇️ Download filtered dataset (CSV)",
    data=fdf.to_csv(index=False).encode("utf-8"),
    file_name="zambia_mtrs_filtered_data.csv",
    mime="text/csv",
    use_container_width=True,
)
st.sidebar.caption(
    f"Source: statistical bulletin workbook · {len(df.columns)-1} indicators · "
    f"{YEARS[0]}–{YEARS[-1]}"
)

# ============================================================================
# TOP BANNER
# ============================================================================

latest_year = sel_years[-1] if sel_years else YEARS[-1]
prior_year = sel_years[-2] if len(sel_years) > 1 else None

st.markdown(
    f"""
    <div class="top-banner">
        <div style="font-size:1.55rem; font-weight:800;">Zambia Medium-Term Revenue Strategy (MTRS) — Executive Dashboard</div>
        <div style="opacity:0.9; margin-top:4px;">Revenue administration performance, {sel_years[0] if sel_years else ''}–{latest_year} ·
        Data as reported in the ZRA/MOF statistical bulletin</div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.write("")

# ============================================================================
# EXECUTIVE KPI SECTION
# ============================================================================

section_header("Executive KPI Summary", "📌")

kpi_defs = [
    ("Tax Revenue", "Tax Revenue", fmt_kwacha, False),
    ("Tax Revenue (% of GDP)", "Tax Revenue (% of GDP)", fmt_pct, True),
    ("Direct Taxes", "Direct Taxes", fmt_kwacha, False),
    ("Indirect Taxes", "Indirect Taxes", fmt_kwacha, False),
    ("Trade Taxes", "Trade Taxes", fmt_kwacha, False),
    ("Pay As You Earn (PAYE)", "Pay As You Earn (PAYE)", fmt_kwacha, False),
    ("Company Tax", "Company Tax", fmt_kwacha, False),
    ("Cost of Collection (% of gross)", "Cost of collection as a % of gross collections", fmt_pct, True),
    ("Value of Imports", "Value of Imports", fmt_kwacha, False),
    ("Value of Exports", "Value of Exports", fmt_kwacha, False),
    ("Registered Importers", "No. of Importers", lambda v: f"{v:,.0f}", False),
    ("Registered Exporters", "No. of Exporters", lambda v: f"{v:,.0f}", False),
]
kpi_defs = [k for k in kpi_defs if k[1] in fdf.columns]

kpi_rows = [kpi_defs[i:i + 4] for i in range(0, len(kpi_defs), 4)]
for row in kpi_rows:
    cols = st.columns(len(row))
    for c, (label, colname, fmtfn, is_ratio) in zip(cols, row):
        series = fdf.set_index("Year")[colname]
        latest_val = series.dropna().iloc[-1] if series.dropna().shape[0] else None
        delta = yoy(series)
        delta_str = f"{delta*100:+.1f}% YoY" if delta is not None else None
        c.metric(label, fmtfn(latest_val) if latest_val is not None else "n/a", delta_str)

trade_balance_latest = None
if "Value of Exports" in fdf.columns and "Value of Imports" in fdf.columns:
    exp = fdf.set_index("Year")["Value of Exports"].dropna()
    imp = fdf.set_index("Year")["Value of Imports"].dropna()
    if len(exp) and len(imp):
        trade_balance_latest = exp.iloc[-1] - imp.iloc[-1]

if trade_balance_latest is not None:
    sign = "surplus" if trade_balance_latest >= 0 else "deficit"
    insight_box(
        f"Zambia recorded a trade {sign} of {fmt_kwacha(abs(trade_balance_latest))} in {latest_year}, "
        f"reflecting the balance between recorded export and import values reported to ZRA."
    )

# ============================================================================
# TABS
# ============================================================================

tab_labels = [
    "Revenue Performance",
    "Taxpayer Segments",
    "Administration & Compliance",
    "Customs & Trade Summary",
    "Trade by Commodity",
    "Trading Partners",
    "Border Posts",
    "Data & Download",
]
tabs = st.tabs(tab_labels)

# ---------------------------------------------------------------------------
# TAB 1 — REVENUE PERFORMANCE
# ---------------------------------------------------------------------------
with tabs[0]:
    section_header("Tax Revenue Trend", "📈")
    if "Tax Revenue" in fdf.columns:
        fig = px.line(fdf, x="Year", y="Tax Revenue", markers=True,
                       color_discrete_sequence=[PRIMARY])
        fig.update_layout(yaxis_title="ZMW million", template="plotly_white", height=380)
        st.plotly_chart(fig, use_container_width=True)
        insight_box(trend_insight(fdf, "Tax Revenue", "Total tax revenue"))

    col1, col2 = st.columns(2)
    with col1:
        section_header("Revenue by Broad Tax Category", "🧾")
        cats = [c for c in ["Direct Taxes", "Indirect Taxes", "Trade Taxes"] if c in fdf.columns]
        if cats:
            melt = fdf.melt(id_vars="Year", value_vars=cats, var_name="Category", value_name="ZMW million")
            fig = px.bar(melt, x="Year", y="ZMW million", color="Category", barmode="stack",
                         color_discrete_sequence=PALETTE)
            fig.update_layout(template="plotly_white", height=360)
            st.plotly_chart(fig, use_container_width=True)
            latest_row = fdf.set_index("Year").loc[latest_year, cats]
            insight_box(ranking_insight(latest_row, "broad tax category collections", year=latest_year))

    with col2:
        section_header(f"Tax Head Composition, {latest_year}", "🥧")
        heads = [c for c in ["Company Tax", "Pay As You Earn (PAYE)", "Withholding Tax & Other taxes",
                              "Rental Income Tax", "Extraction Royalty", "Excise Duties", "Domestic VAT",
                              "VAT on Imports", "Insurance Premium Levy", "Import Tariffs", "Export Duty",
                              "Carbon Tax"] if c in fdf.columns]
        if heads:
            latest_row = fdf.set_index("Year").loc[latest_year, heads].dropna()
            latest_row = latest_row[latest_row > 0]
            fig = px.pie(values=latest_row.values, names=latest_row.index, hole=0.45,
                         color_discrete_sequence=PALETTE)
            fig.update_layout(template="plotly_white", height=360)
            st.plotly_chart(fig, use_container_width=True)
            insight_box(ranking_insight(latest_row, "individual tax head collections", year=latest_year))

    section_header("Revenue as % of GDP", "📐")
    gdp_cols = [c for c in cols_in_section(META, "revenue_gdp", fdf.columns) if c not in CONST_COLS]
    default_gdp = [c for c in ["Tax Revenue (% of GDP)", "Direct Taxes (Revenue as % of GDP)",
                                "Indirect Taxes (Revenue as % of GDP)", "Trade Taxes (Revenue as % of GDP)"]
                   if c in gdp_cols]
    if not default_gdp:
        default_gdp = gdp_cols[:4]
    pick_gdp = st.multiselect("Series to plot", gdp_cols, default=default_gdp, key="gdp_pick")
    if pick_gdp:
        melt = fdf.melt(id_vars="Year", value_vars=pick_gdp, var_name="Series", value_name="Share")
        melt["Share (%)"] = melt["Share"] * 100
        fig = px.line(melt, x="Year", y="Share (%)", color="Series", markers=True,
                      color_discrete_sequence=PALETTE)
        fig.update_layout(template="plotly_white", height=380, yaxis_title="% of GDP")
        st.plotly_chart(fig, use_container_width=True)
        main_gdp_col = pick_gdp[0]
        insight_box(trend_insight(fdf, main_gdp_col, main_gdp_col.split(" (")[0], is_pct=True))

    if "Public sector" in fdf.columns and "Private sector" in fdf.columns:
        section_header("Revenue Contribution by Ownership Sector", "🏛️")
        melt = fdf.melt(id_vars="Year", value_vars=["Public sector", "Private sector"],
                         var_name="Sector", value_name="ZMW million")
        fig = px.bar(melt, x="Year", y="ZMW million", color="Sector", barmode="group",
                     color_discrete_sequence=[PRIMARY, SECONDARY])
        fig.update_layout(template="plotly_white", height=340)
        st.plotly_chart(fig, use_container_width=True)
        latest_row = fdf.set_index("Year").loc[latest_year, ["Public sector", "Private sector"]]
        insight_box(ranking_insight(latest_row, "sector revenue contribution", year=latest_year))

# ---------------------------------------------------------------------------
# TAB 2 — TAXPAYER SEGMENTS
# ---------------------------------------------------------------------------
with tabs[1]:
    section_header("Revenue Mobilised by Taxpayer Segment", "🏢")
    seg_cols = [c for c in ["Large", "Medium", "Small"] if c in fdf.columns]
    if seg_cols:
        col1, col2 = st.columns([2, 1])
        with col1:
            melt = fdf.melt(id_vars="Year", value_vars=seg_cols, var_name="Segment", value_name="ZMW million")
            fig = px.area(melt, x="Year", y="ZMW million", color="Segment",
                          color_discrete_sequence=[PRIMARY, SECONDARY, ACCENT])
            fig.update_layout(template="plotly_white", height=400)
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            latest_row = fdf.set_index("Year").loc[latest_year, seg_cols]
            fig2 = px.pie(values=latest_row.values, names=latest_row.index, hole=0.5,
                          color_discrete_sequence=[PRIMARY, SECONDARY, ACCENT])
            fig2.update_layout(template="plotly_white", height=400, title=f"{latest_year} Share")
            st.plotly_chart(fig2, use_container_width=True)
        insight_box(ranking_insight(latest_row, "taxpayer segment revenue", year=latest_year))
        insight_box(trend_insight(fdf, seg_cols[0], f"{seg_cols[0]} taxpayer revenue"))
    else:
        st.info("No taxpayer segment columns available in the current selection.")

    if "Government funding" in fdf.columns and "Government funding" not in CONST_COLS:
        section_header("ZRA Government Funding", "🏦")
        fig = px.line(fdf, x="Year", y="Government funding", markers=True,
                      color_discrete_sequence=[ACCENT])
        fig.update_layout(template="plotly_white", height=320, yaxis_title="ZMW million")
        st.plotly_chart(fig, use_container_width=True)
        insight_box(trend_insight(fdf, "Government funding", "Government funding to ZRA"))

# ---------------------------------------------------------------------------
# TAB 3 — ADMINISTRATION & COMPLIANCE
# ---------------------------------------------------------------------------
with tabs[2]:
    col1, col2 = st.columns(2)
    with col1:
        section_header("Cost of Collection", "⚙️")
        if "Cost of collection as a % of gross collections" in fdf.columns:
            s = fdf["Cost of collection as a % of gross collections"] * 100
            fig = px.line(fdf, x="Year", y=s, markers=True, color_discrete_sequence=[ACCENT])
            fig.update_layout(template="plotly_white", height=340, yaxis_title="% of gross collections")
            st.plotly_chart(fig, use_container_width=True)
            insight_box(trend_insight(fdf, "Cost of collection as a % of gross collections",
                                       "The cost of collection", is_pct=True))
    with col2:
        section_header("Payment Channel Mix", "💳")
        chan_cols = [c for c in ["e-Payment", "Cash or RTGS or Cheque"] if c in fdf.columns]
        if chan_cols:
            melt = fdf.melt(id_vars="Year", value_vars=chan_cols, var_name="Channel", value_name="Share")
            melt["Share (%)"] = melt["Share"] * 100
            fig = px.bar(melt, x="Year", y="Share (%)", color="Channel", barmode="group",
                         color_discrete_sequence=[PRIMARY, SECONDARY])
            fig.update_layout(template="plotly_white", height=340)
            st.plotly_chart(fig, use_container_width=True)
            latest_row = fdf.set_index("Year").loc[latest_year, chan_cols]
            insight_box(
                f"Electronic payment accounted for {fmt_pct(latest_row.get('e-Payment', float('nan')))} of tax "
                f"payment channels in {latest_year}, versus {fmt_pct(latest_row.get('Cash or RTGS or Cheque', float('nan')))} "
                f"through cash, RTGS or cheque."
            )

    section_header("VAT Refunds", "💰")
    ref_cols = [c for c in ["C. Value added tax refunds", "Total refunds"] if c in fdf.columns]
    if ref_cols:
        melt = fdf.melt(id_vars="Year", value_vars=ref_cols, var_name="Series", value_name="ZMW million")
        fig = px.line(melt, x="Year", y="ZMW million", color="Series", markers=True,
                      color_discrete_sequence=[PRIMARY, ACCENT])
        fig.update_layout(template="plotly_white", height=360)
        st.plotly_chart(fig, use_container_width=True)
        insight_box(trend_insight(fdf, ref_cols[0], ref_cols[0]))

    mining_cols = [c for c in fdf.columns if "MiningPaid VAT refunds" in c or "Non-Mining_Paid VAT refunds" in c]
    if mining_cols:
        section_header("Paid VAT Refunds — Mining vs Non-Mining", "⛏️")
        melt = fdf.melt(id_vars="Year", value_vars=mining_cols, var_name="Sector", value_name="ZMW million")
        melt["Sector"] = melt["Sector"].str.replace("\xa0", "", regex=False)
        fig = px.bar(melt, x="Year", y="ZMW million", color="Sector", barmode="group",
                     color_discrete_sequence=[PRIMARY, SECONDARY])
        fig.update_layout(template="plotly_white", height=340)
        st.plotly_chart(fig, use_container_width=True)
        latest_row = fdf.set_index("Year").loc[latest_year, mining_cols]
        insight_box(ranking_insight(latest_row, "paid VAT refunds by sector", year=latest_year))

    pending_cols = [c for c in fdf.columns if "Distribution_approved_VAT_refund_claims_pending_payment" in c
                    and "Total" not in c]
    if pending_cols:
        section_header("Approved VAT Refund Claims Pending Payment", "⏳")
        melt = fdf.melt(id_vars="Year", value_vars=pending_cols, var_name="Sector", value_name="ZMW million")
        melt["Sector"] = melt["Sector"].str.replace("_Distribution_approved_VAT_refund_claims_pending_payment", "",
                                                       regex=False).str.strip()
        fig = px.area(melt, x="Year", y="ZMW million", color="Sector", color_discrete_sequence=[PRIMARY, SECONDARY])
        fig.update_layout(template="plotly_white", height=340)
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# TAB 4 — CUSTOMS & TRADE SUMMARY
# ---------------------------------------------------------------------------
with tabs[3]:
    section_header("Imports vs Exports", "🚢")
    if "Value of Imports" in fdf.columns and "Value of Exports" in fdf.columns:
        melt = fdf.melt(id_vars="Year", value_vars=["Value of Imports", "Value of Exports"],
                         var_name="Flow", value_name="ZMW million")
        fig = px.line(melt, x="Year", y="ZMW million", color="Flow", markers=True,
                      color_discrete_sequence=[ACCENT, PRIMARY])
        fig.update_layout(template="plotly_white", height=380)
        st.plotly_chart(fig, use_container_width=True)

        bal = fdf.set_index("Year")["Value of Exports"] - fdf.set_index("Year")["Value of Imports"]
        fig_bal = go.Figure(go.Bar(x=bal.index, y=bal.values,
                                    marker_color=[PRIMARY if v >= 0 else ACCENT for v in bal.values]))
        fig_bal.update_layout(template="plotly_white", height=280, title="Trade Balance (Exports − Imports)",
                               yaxis_title="ZMW million")
        st.plotly_chart(fig_bal, use_container_width=True)
        insight_box(trend_insight(fdf, "Value of Exports", "Export value"))
        insight_box(trend_insight(fdf, "Value of Imports", "Import value"))

    col1, col2 = st.columns(2)
    with col1:
        section_header("Registered Traders", "🧑‍💼")
        trader_cols = [c for c in ["No. of Importers", "No. of Exporters"] if c in fdf.columns]
        if trader_cols:
            melt = fdf.melt(id_vars="Year", value_vars=trader_cols, var_name="Type", value_name="Count")
            fig = px.line(melt, x="Year", y="Count", color="Type", markers=True,
                         color_discrete_sequence=[PRIMARY, SECONDARY])
            fig.update_layout(template="plotly_white", height=340)
            st.plotly_chart(fig, use_container_width=True)
            insight_box(trend_insight(fdf, trader_cols[0], trader_cols[0], unit="count"))
    with col2:
        section_header("Customs Entries Processed", "📋")
        entry_cols = [c for c in ["No. of Import Entries", "No. of Export Entries"] if c in fdf.columns]
        if entry_cols:
            melt = fdf.melt(id_vars="Year", value_vars=entry_cols, var_name="Type", value_name="Entries")
            fig = px.bar(melt, x="Year", y="Entries", color="Type", barmode="group",
                        color_discrete_sequence=[PRIMARY, SECONDARY])
            fig.update_layout(template="plotly_white", height=340)
            st.plotly_chart(fig, use_container_width=True)

    vdp_cols = [c for c in ["Non-Taxable_Value for duty purposes (VDP) from taxable and non-taxable transactions",
                             "Taxable_Value for duty purposes (VDP) from taxable and non-taxable transactions"]
                if c in fdf.columns]
    if vdp_cols:
        section_header("Value for Duty Purposes (VDP)", "📦")
        melt = fdf.melt(id_vars="Year", value_vars=vdp_cols, var_name="Type", value_name="ZMW million")
        melt["Type"] = melt["Type"].str.replace(
            " for duty purposes (VDP) from taxable and non-taxable transactions", "", regex=False)
        fig = px.bar(melt, x="Year", y="ZMW million", color="Type", barmode="stack",
                    color_discrete_sequence=[PRIMARY, SECONDARY])
        fig.update_layout(template="plotly_white", height=340)
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# TAB 5 — TRADE BY COMMODITY
# ---------------------------------------------------------------------------
with tabs[4]:
    for section_key, title, icon in [("imports_hs", "Imports by Commodity Section", "📥"),
                                      ("exports_hs", "Exports by Commodity Section", "📤")]:
        section_header(f"{title}, {latest_year}", icon)
        cols_all = [c for c in cols_in_section(META, section_key, fdf.columns) if c not in CONST_COLS]
        if search_term:
            cols_all = [c for c in cols_all if search_term.lower() in c.lower()] or cols_all
        if not cols_all:
            st.info("No data available for this section.")
            continue
        latest_row = fdf.set_index("Year").loc[latest_year, cols_all].dropna().sort_values(ascending=False)
        top = latest_row.head(top_n)
        labels = [short_label(i) for i in top.index]
        fig = px.bar(x=top.values, y=labels, orientation="h",
                    color_discrete_sequence=[PRIMARY if "imports" in section_key else SECONDARY])
        fig.update_layout(template="plotly_white", height=max(320, 28 * len(top)),
                          xaxis_title="ZMW million", yaxis_title="", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)
        insight_box(ranking_insight(latest_row, title, year=latest_year))

        top5_cols = latest_row.head(5).index.tolist()
        if len(sel_years) > 1 and top5_cols:
            trend_melt = fdf.melt(id_vars="Year", value_vars=top5_cols, var_name="Commodity", value_name="ZMW million")
            trend_melt["Commodity"] = trend_melt["Commodity"].apply(short_label)
            fig2 = px.line(trend_melt, x="Year", y="ZMW million", color="Commodity", markers=True,
                          color_discrete_sequence=PALETTE)
            fig2.update_layout(template="plotly_white", height=340, title="Trend — Top 5 Commodities")
            st.plotly_chart(fig2, use_container_width=True)

# ---------------------------------------------------------------------------
# TAB 6 — TRADING PARTNERS
# ---------------------------------------------------------------------------
with tabs[5]:
    for section_key, title, icon in [("partners_imports", "Imports by Trading Partner", "🌍"),
                                      ("partners_exports", "Exports by Trading Partner", "🌐")]:
        section_header(f"{title}, {latest_year}", icon)
        cols_all = [c for c in cols_in_section(META, section_key, fdf.columns)
                    if c not in CONST_COLS and not c.lower().startswith(("total", "totals"))]
        if search_term:
            filtered = [c for c in cols_all if search_term.lower() in c.lower()]
            cols_all = filtered or cols_all
        if not cols_all:
            st.info("No data available for this section.")
            continue
        latest_row = fdf.set_index("Year").loc[latest_year, cols_all].dropna().sort_values(ascending=False)
        top = latest_row.head(top_n)
        clean_names = [c.replace("_imports", "").replace("_exports", "") for c in top.index]
        fig = px.bar(x=top.values, y=clean_names, orientation="h",
                    color_discrete_sequence=[ACCENT if "imports" in section_key else PRIMARY])
        fig.update_layout(template="plotly_white", height=max(320, 30 * len(top)),
                          xaxis_title="ZMW million", yaxis_title="", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)
        insight_box(ranking_insight(latest_row, title, year=latest_year))

        top3_cols = latest_row.head(3).index.tolist()
        if len(sel_years) > 1 and top3_cols:
            trend_melt = fdf.melt(id_vars="Year", value_vars=top3_cols, var_name="Partner", value_name="ZMW million")
            trend_melt["Partner"] = trend_melt["Partner"].str.replace("_imports", "", regex=False)\
                .str.replace("_exports", "", regex=False)
            fig2 = px.line(trend_melt, x="Year", y="ZMW million", color="Partner", markers=True,
                          color_discrete_sequence=PALETTE)
            fig2.update_layout(template="plotly_white", height=320, title="Trend — Top 3 Partners")
            st.plotly_chart(fig2, use_container_width=True)

# ---------------------------------------------------------------------------
# TAB 7 — BORDER POSTS
# ---------------------------------------------------------------------------
with tabs[6]:
    port_sections = [
        ("export_port_exit", "Export Value by Border Post", "🛃"),
        ("import_port_exit", "Import Value by Border Post (Exit Recorded)", "🛃"),
        ("value_imports_port", "Value of Imports by Border Post (Entry)", "📦"),
        ("rexports_port", "Re-exports by Border Post", "🔁"),
        ("reimports_port", "Re-imports by Border Post", "🔁"),
    ]
    port_pick = st.selectbox("Border post metric", [p[1] for p in port_sections])
    section_key, title, icon = next(p for p in port_sections if p[1] == port_pick)
    section_header(f"{title}, {latest_year}", icon)
    cols_all = [c for c in cols_in_section(META, section_key, fdf.columns) if c not in CONST_COLS]
    if search_term:
        filtered = [c for c in cols_all if search_term.lower() in c.lower()]
        cols_all = filtered or cols_all
    if cols_all:
        latest_row = fdf.set_index("Year").loc[latest_year, cols_all].dropna().sort_values(ascending=False)
        top = latest_row.head(top_n)
        clean_names = [re.sub(r"_(export|import)_port_exit|_value_imports|_rexports_by_port|_reimports_by_port",
                              "", c) for c in top.index]
        fig = px.bar(x=top.values, y=clean_names, orientation="h", color_discrete_sequence=[PRIMARY])
        fig.update_layout(template="plotly_white", height=max(320, 30 * len(top)),
                          xaxis_title="ZMW million", yaxis_title="", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)
        insight_box(ranking_insight(latest_row, title, year=latest_year))

        top_col = latest_row.index[0]
        if len(sel_years) > 1:
            st.plotly_chart(
                px.line(fdf, x="Year", y=top_col, markers=True, color_discrete_sequence=[SECONDARY])
                .update_layout(template="plotly_white", height=300,
                              title=f"Trend — {re.sub(r'_.*', '', top_col)}", yaxis_title="ZMW million"),
                use_container_width=True,
            )
    else:
        st.info("No data available for this section.")

# ---------------------------------------------------------------------------
# TAB 8 — DATA & DOWNLOAD
# ---------------------------------------------------------------------------
with tabs[7]:
    section_header("Underlying Data (Filtered)", "🗂️")
    st.caption(
        "This table reflects the current year-range filter. Use the search box in the sidebar "
        "together with the sidebar download button, or filter columns below by section."
    )
    section_titles = sorted(set(m["section_title"] for m in META.values()))
    pick_section = st.multiselect("Show columns from section(s)", section_titles,
                                  default=["Revenue Performance"])
    if pick_section:
        show_cols = ["Year"] + [c for c, m in META.items()
                                if m["section_title"] in pick_section and c in fdf.columns]
    else:
        show_cols = fdf.columns.tolist()
    st.dataframe(fdf[show_cols], use_container_width=True, height=420)
    st.download_button(
        "⬇️ Download this view (CSV)",
        data=fdf[show_cols].to_csv(index=False).encode("utf-8"),
        file_name="zambia_mtrs_view.csv",
        mime="text/csv",
    )

    section_header("Column Dictionary", "📖")
    dict_df = pd.DataFrame([
        {"Column": c, "Section": m["section_title"], "Unit": m["unit"]}
        for c, m in META.items() if c in df.columns and c != "Year"
    ])
    st.dataframe(dict_df, use_container_width=True, height=320)

st.markdown("---")
st.caption(
    "Executive dashboard generated from the uploaded statistical bulletin. Figures are as reported; "
    "no synthetic values were introduced. For policy use, cross-check against the official MOF/ZRA "
    "publication."
)
