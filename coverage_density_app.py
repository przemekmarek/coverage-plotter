"""
Coverage Density Timeline — Streamlit app
==========================================
Upload a tab- or comma-separated file with:
  - dates in the first column (e.g. "Nov-20", "2020-11", "01/11/2020" ...)
  - pairs of columns named  <label>_ws  and  <label>_coverage
The app draws a horizontal density bar per label, where the colour opacity
of each monthly cell is proportional to data coverage (0% = invisible,
100% = fully saturated).

Run with:  streamlit run coverage_density_app.py
Requires:  streamlit, pandas, plotly
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ----------------------------------------------------------------------------
# Colour schemes — base colours cycled across labels (top to bottom)
# ----------------------------------------------------------------------------
COLOR_SCHEMES = {
    "Caribbean": [
        "#00A6A6", "#0081A7", "#02C39A", "#05668D", "#00CFC1",
        "#1B9AAA", "#3DCCC7", "#007F5F",
    ],
    "Blood Orange": [
        "#D62828", "#F77F00", "#E85D04", "#9D0208", "#FF6D00",
        "#DC2F02", "#FAA307", "#BF3100",
    ],
    "Autumn Leaves": [
        "#B5651D", "#8B4513", "#D2691E", "#A0522D", "#CC7722",
        "#806000", "#C46210", "#6F4E37",
    ],
}


def hex_to_rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ----------------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------------
def parse_dates(series: pd.Series) -> pd.Series:
    """Try a few common date formats, fall back to pandas' general parser."""
    for fmt in ("%b-%y", "%b-%Y", "%Y-%m", "%m/%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return pd.to_datetime(series, format=fmt)
        except (ValueError, TypeError):
            continue
    return pd.to_datetime(series, dayfirst=True, errors="coerce")


@st.cache_data
def load_data(file) -> pd.DataFrame:
    name = getattr(file, "name", "")
    sep = "\t" if name.lower().endswith((".txt", ".tsv")) else None
    df = pd.read_csv(file, sep=sep, engine="python")
    df = df.rename(columns={df.columns[0]: "Date"})
    df["Date"] = parse_dates(df["Date"])
    df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    return df


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Coverage Density Timeline", layout="wide")
st.title("Data coverage density timeline")

uploaded = st.sidebar.file_uploader(
    "Upload data file (.txt / .tsv / .csv)", type=["txt", "tsv", "csv"]
)

if uploaded is None:
    st.info("Upload a file with a date column and `<label>_ws` / `<label>_coverage` column pairs.")
    st.stop()

df = load_data(uploaded)

# Identify coverage columns and their labels
cov_cols = [c for c in df.columns if c.lower().endswith("_coverage")]
if not cov_cols:
    st.error("No columns ending in `_coverage` were found in this file.")
    st.stop()

labels = [c[: -len("_coverage")] for c in cov_cols]
ws_lookup = {lab: f"{lab}_ws" if f"{lab}_ws" in df.columns else None for lab in labels}

# --- Sidebar controls --------------------------------------------------------
st.sidebar.header("Display options")

scheme_name = st.sidebar.selectbox("Colour scheme", list(COLOR_SCHEMES.keys()))
palette = COLOR_SCHEMES[scheme_name]

st.sidebar.subheader("Data streams")
selected = [lab for lab in labels if st.sidebar.checkbox(lab, value=True, key=f"cb_{lab}")]

min_d, max_d = df["Date"].min().to_pydatetime(), df["Date"].max().to_pydatetime()
date_range = st.sidebar.slider(
    "Date range",
    min_value=min_d,
    max_value=max_d,
    value=(min_d, max_d),
    format="MMM YYYY",
)

bar_height = st.sidebar.slider("Row height (px)", 30, 120, 60)

if not selected:
    st.warning("Tick at least one data stream in the sidebar.")
    st.stop()

# --- Filter ------------------------------------------------------------------
mask = (df["Date"] >= date_range[0]) & (df["Date"] <= date_range[1])
dfp = df.loc[mask]
if dfp.empty:
    st.warning("No data in the selected date range.")
    st.stop()

# ----------------------------------------------------------------------------
# Plot — one single-row heatmap trace per label; opacity scales with coverage
# ----------------------------------------------------------------------------
fig = go.Figure()

# Reverse so the first label appears at the top
plot_order = list(reversed(selected))

for i, lab in enumerate(plot_order):
    base_idx = selected.index(lab)  # keep colour tied to original order
    r, g, b = hex_to_rgb(palette[base_idx % len(palette)])
    colorscale = [
        [0.0, f"rgba({r},{g},{b},0)"],
        [1.0, f"rgba({r},{g},{b},1)"],
    ]

    cov = pd.to_numeric(dfp[f"{lab}_coverage"], errors="coerce").fillna(0)
    ws_col = ws_lookup[lab]
    ws = (
        pd.to_numeric(dfp[ws_col], errors="coerce")
        if ws_col
        else pd.Series([float("nan")] * len(dfp), index=dfp.index)
    )

    fig.add_trace(
        go.Heatmap(
            x=dfp["Date"],
            y=[lab] * len(dfp),
            z=cov,
            zmin=0,
            zmax=100,
            colorscale=colorscale,
            showscale=False,
            xgap=1,
            ygap=8,
            customdata=ws,
            hovertemplate=(
                f"<b>{lab}</b><br>"
                "%{x|%b %Y}<br>"
                "Coverage: %{z:.1f}%<br>"
                "Mean WS: %{customdata:.2f} m/s"
                "<extra></extra>"
            ),
        )
    )

fig.update_layout(
    height=max(300, bar_height * len(selected) + 120),
    margin=dict(l=10, r=20, t=30, b=40),
    plot_bgcolor="white",
    xaxis=dict(
        title="",
        showgrid=True,
        gridcolor="rgba(0,0,0,0.08)",
        dtick="M3",
        tickformat="%b<br>%Y",
        ticklabelmode="period",
    ),
    yaxis=dict(
        title="",
        categoryorder="array",
        categoryarray=plot_order,
        tickfont=dict(size=13),
    ),
)

st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Cell opacity is proportional to monthly data coverage "
    "(transparent = 0%, fully saturated = 100%). Hover for details."
)

# Optional: show the underlying coverage table
with st.expander("Show coverage table"):
    show_cols = ["Date"] + [f"{lab}_coverage" for lab in selected]
    st.dataframe(
        dfp[show_cols].set_index("Date").style.format("{:.1f}"),
        use_container_width=True,
    )
