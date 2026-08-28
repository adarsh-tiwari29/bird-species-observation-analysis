"""
Bird Species Observation Analysis — Interactive Streamlit Dashboard
==================================================================

Project : Bird Species Observation Analysis
Type    : EDA / Data Visualization
Member  : Adarsh Shrikant Tiwari

Architecture
------------
    config      -> AppConfig, Palette, Ordering, ParkRegistry
    data layer  -> Database (connection + cached query execution)
    filtering   -> FilterState (dataclass) -> QueryScope (WHERE + params)
    ui helpers  -> UI (sql viewer, chart notes, chart factories)
    pages       -> @page("Name") decorated renderers, auto-registered
    entrypoint  -> Dashboard.run()

Every figure is driven by a live SQL query against `bird_observations.db`,
satisfying the project guideline: "Store data in an SQL database for
visualization." Sidebar selections are compiled into a parameterised SQL
WHERE clause, so the database performs the filtering and aggregation
rather than pandas.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Sequence, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# ===========================================================================
# SECTION 1 — CONFIGURATION
# ===========================================================================

class AppConfig:
    """Static application-level settings."""

    DB_PATH = "bird_observations.db"
    PAGE_TITLE = "Bird Species Observation Analysis"
    PAGE_ICON = "🐦"
    LAYOUT = "wide"
    SIDEBAR_STATE = "expanded"

    DATA_CAPTION = (
        "Data: U.S. National Park Service bird monitoring, 11 park units, "
        "7 May – 19 July 2018. All charts are driven by live SQL queries."
    )
    SUBTITLE = "Forest vs Grassland habitats · 2018 breeding season"


class Palette:
    """Colour constants shared by every chart, so habitats read consistently."""

    HABITAT = {"Forest": "#2f9e8f", "Grassland": "#e0a458"}
    NEUTRAL = "#6b7a8f"
    WATCHLIST = {"PIF Watchlist": "#e0555f", "Not listed": "#2f9e8f"}
    SEX = ["#4a5d70", "#2f9e8f", "#e0a458"]
    DISTANCE = ["#2f9e8f", "#7fc9be", "#294a56"]
    QUALITATIVE = ["#2f9e8f", "#e0a458", "#8e7cc3", "#e0555f", "#5b9bd5"]

    # Surface / typography tokens driving the CSS layer
    INK = "#0e1620"
    SURFACE = "#16212e"
    SURFACE_ALT = "#1d2b3a"
    BORDER = "#2a3b4d"
    TEXT = "#e6edf3"
    MUTED = "#93a4b5"
    ACCENT = "#2f9e8f"
    GRID = "rgba(255,255,255,0.06)"


class Theme:
    """All look-and-feel: page CSS, the Plotly template and the KPI cards."""

    FONT = (
        "'IBM Plex Sans', 'Segoe UI', -apple-system, BlinkMacSystemFont, "
        "sans-serif"
    )

    CSS = f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

      html, body, [class*="css"], .stApp {{
          font-family: {FONT};
          background: {Palette.INK};
          color: {Palette.TEXT};
      }}

      /* ---- Sidebar ---- */
      section[data-testid="stSidebar"] {{
          background: linear-gradient(180deg, #101a26 0%, #0b1219 100%);
          border-right: 1px solid {Palette.BORDER};
      }}
      section[data-testid="stSidebar"] .stRadio > label {{ display:none; }}
      section[data-testid="stSidebar"] div[role="radiogroup"] label {{
          padding: 7px 12px;
          border-radius: 8px;
          margin-bottom: 2px;
          transition: background .15s ease, color .15s ease;
      }}
      section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{
          background: rgba(47,158,143,0.12);
      }}

      /* ---- Typography ---- */
      h1 {{
          font-weight: 700 !important;
          letter-spacing: -0.02em;
          font-size: 2.15rem !important;
          padding-bottom: .35rem;
          border-bottom: 2px solid {Palette.ACCENT};
          display: inline-block;
      }}
      h2, h3 {{
          font-weight: 600 !important;
          letter-spacing: -0.01em;
          color: {Palette.TEXT};
      }}
      h3 {{ font-size: 1.18rem !important; }}
      h3::before {{
          content: "";
          display: inline-block;
          width: 4px; height: 15px;
          margin-right: 10px;
          border-radius: 2px;
          background: {Palette.ACCENT};
          transform: translateY(1px);
      }}

      /* ---- KPI cards ---- */
      .kpi-card {{
          background: linear-gradient(160deg, {Palette.SURFACE_ALT} 0%, {Palette.SURFACE} 100%);
          border: 1px solid {Palette.BORDER};
          border-top: 3px solid {Palette.ACCENT};
          border-radius: 12px;
          padding: 16px 18px 14px 18px;
          height: 100%;
          box-shadow: 0 2px 10px rgba(0,0,0,.28);
      }}
      .kpi-label {{
          font-size: .72rem;
          letter-spacing: .09em;
          text-transform: uppercase;
          color: {Palette.MUTED};
          margin-bottom: 6px;
      }}
      .kpi-value {{
          font-size: 1.9rem;
          font-weight: 700;
          line-height: 1.1;
          color: {Palette.TEXT};
      }}

      /* ---- Tables ---- */
      div[data-testid="stDataFrame"] {{
          border: 1px solid {Palette.BORDER};
          border-radius: 10px;
          overflow: hidden;
      }}

      /* ---- Callouts ---- */
      div[data-testid="stAlert"] {{
          border-radius: 10px;
          border-left-width: 4px;
      }}

      /* ---- Expander (SQL viewer) ---- */
      div[data-testid="stExpander"] {{
          border: 1px solid {Palette.BORDER};
          border-radius: 10px;
          background: {Palette.SURFACE};
      }}
      code, pre, .stCode {{ font-family: 'IBM Plex Mono', monospace !important; }}

      /* ---- Widgets ---- */
      .stSlider [data-baseweb="slider"] div[role="slider"] {{
          border-color: {Palette.ACCENT};
      }}
      .stButton > button {{
          border-radius: 8px;
          font-weight: 600;
          border: 1px solid {Palette.ACCENT};
      }}
      span[data-baseweb="tag"] {{
          background-color: {Palette.ACCENT} !important;
          border-radius: 6px !important;
      }}
      button[data-baseweb="tab"] {{ font-weight: 600; }}

      hr {{ border-color: {Palette.BORDER}; opacity: .6; }}
      footer, #MainMenu {{ visibility: hidden; }}
      .block-container {{ padding-top: 2.4rem; max-width: 1500px; }}
    </style>
    """

    PLOTLY_LAYOUT = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Sans, Segoe UI, sans-serif",
                  size=13, color=Palette.TEXT),
        title_font=dict(size=15, color=Palette.TEXT),
        margin=dict(l=10, r=10, t=52, b=10),
        xaxis=dict(gridcolor=Palette.GRID, zerolinecolor=Palette.GRID,
                   linecolor=Palette.BORDER),
        yaxis=dict(gridcolor=Palette.GRID, zerolinecolor=Palette.GRID,
                   linecolor=Palette.BORDER),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, title_text=""),
        hoverlabel=dict(bgcolor=Palette.SURFACE_ALT,
                        bordercolor=Palette.ACCENT,
                        font_size=12),
        bargap=0.24,
    )

    @staticmethod
    def inject() -> None:
        st.markdown(Theme.CSS, unsafe_allow_html=True)

    @staticmethod
    def stylise(fig):
        """Apply the shared Plotly look to any figure."""
        fig.update_layout(**Theme.PLOTLY_LAYOUT)
        return fig

    @staticmethod
    def kpi(column, label: str, value) -> None:
        """Render a metric as a bordered card instead of the default st.metric."""
        column.markdown(
            f"<div class='kpi-card'>"
            f"<div class='kpi-label'>{label}</div>"
            f"<div class='kpi-value'>{value}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    @staticmethod
    def divider() -> None:
        st.markdown(
            f"<hr style='margin:1.9rem 0 1.5rem 0;border:none;height:1px;"
            f"background:linear-gradient(90deg,{Palette.ACCENT}55,"
            f"{Palette.BORDER} 45%,transparent);'>",
            unsafe_allow_html=True,
        )

    @staticmethod
    def header(title: str, subtitle: str = "") -> None:
        """Page title with an accent rule and optional standfirst."""
        st.markdown(f"<h1>{title}</h1>", unsafe_allow_html=True)
        if subtitle:
            st.markdown(
                f"<p style='color:{Palette.MUTED};font-size:1.02rem;"
                f"max-width:78ch;margin-top:.6rem;'>{subtitle}</p>",
                unsafe_allow_html=True,
            )


class Ordering:
    """SQL returns rows unordered — these sequences restore meaning."""

    INTERVAL = ["0-2.5 min", "2.5 - 5 min", "5 - 7.5 min", "7.5 - 10 min"]
    DISTURBANCE = [
        "No effect on count",
        "Slight effect on count",
        "Moderate effect on count",
        "Serious effect on count",
    ]
    MONTH = ["May", "June", "July"]


class ParkRegistry:
    """Park codes mapped to their full names for readable labels."""

    NAMES = {
        "ANTI": "Antietam National Battlefield",
        "CATO": "Catoctin Mountain Park",
        "CHOH": "Chesapeake & Ohio Canal NHP",
        "GWMP": "George Washington Memorial Pkwy",
        "HAFE": "Harpers Ferry NHP",
        "MANA": "Manassas National Battlefield",
        "MONO": "Monocacy National Battlefield",
        "NACE": "National Capital East Parks",
        "PRWI": "Prince William Forest Park",
        "ROCR": "Rock Creek Park",
        "WOTR": "Wolf Trap National Park",
    }

    @classmethod
    def label(cls, code: str) -> str:
        return cls.NAMES.get(code, code)


# ===========================================================================
# SECTION 2 — DATA ACCESS LAYER
# ===========================================================================

@st.cache_resource(show_spinner=False)
def _open_connection() -> sqlite3.Connection:
    """
    Open a single shared SQLite connection for the app session.

    check_same_thread=False is required because Streamlit re-runs the script
    on a different thread for each interaction.
    """
    if not os.path.exists(AppConfig.DB_PATH):
        st.error(
            f"Database '{AppConfig.DB_PATH}' not found.\n\n"
            "Run `Bird_Species_Observation_Analysis_EDA.ipynb` first - it "
            "generates the database from the two source Excel workbooks."
        )
        st.stop()
    return sqlite3.connect(AppConfig.DB_PATH, check_same_thread=False)


@st.cache_data(show_spinner=False)
def _execute(sql: str, params: Tuple = ()) -> pd.DataFrame:
    """
    Execute a parameterised SQL query and return the result as a DataFrame.

    Results are cached by (sql, params), so repeating a filter combination is
    instant. Parameters are bound rather than string-formatted, which keeps
    the queries safe and lets SQLite reuse its query plan.
    """
    try:
        return pd.read_sql_query(sql, _open_connection(), params=params)
    except Exception as exc:                      # noqa: BLE001
        st.error(f"SQL query failed: {exc}")
        return pd.DataFrame()


class Database:
    """Thin façade over the SQLite file — all reads funnel through here."""

    TABLES = ("observations", "species_reference", "plot_reference")

    @staticmethod
    def connection() -> sqlite3.Connection:
        return _open_connection()

    @staticmethod
    def query(sql: str, params: Sequence = ()) -> pd.DataFrame:
        return _execute(sql, tuple(params))

    @staticmethod
    def scalar(sql: str, params: Sequence = (), default=0):
        frame = Database.query(sql, params)
        return default if frame.empty else frame.iloc[0, 0]

    @staticmethod
    @st.cache_data(show_spinner=False)
    def distinct_values() -> Dict[str, List[str]]:
        """Fetch the distinct values that populate the sidebar filter widgets."""
        conn = _open_connection()
        pull = lambda sql, col: pd.read_sql_query(sql, conn)[col].tolist()  # noqa: E731
        return {
            "habitats": pull(
                "SELECT DISTINCT Location_Type FROM observations ORDER BY 1",
                "Location_Type",
            ),
            "parks": pull(
                "SELECT DISTINCT Admin_Unit_Code FROM observations ORDER BY 1",
                "Admin_Unit_Code",
            ),
            "observers": pull(
                "SELECT DISTINCT Observer FROM observations ORDER BY 1",
                "Observer",
            ),
            "months": pull(
                "SELECT DISTINCT Month_Name FROM observations ORDER BY Month",
                "Month_Name",
            ),
        }

    @staticmethod
    def schema_overview():
        """Yield (table_name, row_count, column_list) for the SQL Explorer."""
        conn = _open_connection()
        for table in Database.TABLES:
            info = pd.read_sql_query(f"PRAGMA table_info({table})", conn)
            rows = pd.read_sql_query(
                f"SELECT COUNT(*) AS n FROM {table}", conn
            )["n"][0]
            yield table, int(rows), info["name"].tolist()


# ===========================================================================
# SECTION 3 — FILTER STATE -> QUERY SCOPE
# ===========================================================================

@dataclass(frozen=True)
class QueryScope:
    """A compiled WHERE clause plus its positionally-bound parameters."""

    where: str
    params: Tuple

    def bind(self, *extra) -> Tuple:
        """Append trailing parameters (e.g. a LIMIT value) to the bound tuple."""
        return self.params + tuple(extra)


@dataclass
class FilterState:
    """Sidebar selections, in one place, translatable to SQL."""

    habitats: List[str] = field(default_factory=list)
    parks: List[str] = field(default_factory=list)
    months: List[str] = field(default_factory=list)
    observers: List[str] = field(default_factory=list)
    watchlist_only: bool = False
    exclude_flyovers: bool = False

    _COLUMN_MAP = (
        ("habitats", "Location_Type"),
        ("parks", "Admin_Unit_Code"),
        ("months", "Month_Name"),
        ("observers", "Observer"),
    )

    def compile(self) -> QueryScope:
        """
        Translate the sidebar selections into a SQL WHERE clause plus params.

        The clause always begins with "WHERE" so it can be dropped straight
        into a query template.
        """
        clauses: List[str] = []
        params: List = []

        for attribute, column in self._COLUMN_MAP:
            values = getattr(self, attribute)
            if values:
                clauses.append(f"{column} IN ({','.join('?' * len(values))})")
                params.extend(values)

        if self.watchlist_only:
            clauses.append("PIF_Watchlist_Status = 1")
        if self.exclude_flyovers:
            clauses.append("Flyover_Observed = 0")

        where = "WHERE " + " AND ".join(clauses) if clauses else "WHERE 1=1"
        return QueryScope(where, tuple(params))


# ===========================================================================
# SECTION 4 — UI HELPERS
# ===========================================================================

class UI:
    """Small presentation utilities reused across pages."""

    @staticmethod
    def sql(sql: str, params: Sequence = ()) -> None:
        """Render the SQL behind a chart in a collapsed expander."""
        with st.expander("View the SQL behind this chart"):
            st.code(sql.strip(), language="sql")
            if params:
                st.caption(f"Bound parameters: {tuple(params)}")

    @staticmethod
    def note(text: str) -> None:
        """Render a short interpretation note beneath a chart."""
        text = re.sub(r"\*\*(.+?)\*\*", r"<b style='color:#e6edf3'>\1</b>", text)
        st.markdown(
            f"<div style='border-left:3px solid {Palette.ACCENT};"
            f"background:{Palette.SURFACE};border-radius:0 8px 8px 0;"
            f"padding:10px 14px;margin:2px 0 6px 0;font-size:.88rem;"
            f"color:{Palette.MUTED};'>"
            f"<b style='color:{Palette.TEXT};'>Reading this chart:</b> {text}"
            f"</div>",
            unsafe_allow_html=True,
        )

    @staticmethod
    def render(fig, height: int = 420, **layout) -> None:
        """Apply a common layout and push the figure to the page."""
        Theme.stylise(fig)
        fig.update_layout(height=height, **layout)
        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})

    @staticmethod
    def labelled(fig, size: int | None = None, template: str | None = None):
        """Push bar labels outside the bars, optionally formatted."""
        kwargs = {"textposition": "outside"}
        if size:
            kwargs["textfont_size"] = size
        if template:
            kwargs["texttemplate"] = template
        fig.update_traces(**kwargs)
        return fig

    @staticmethod
    def by_habitat(frame: pd.DataFrame, x: str, y: str, **kwargs):
        """Grouped bar chart coloured by habitat — the most repeated pattern."""
        return px.bar(
            frame, x=x, y=y, color="Habitat", barmode="group",
            color_discrete_map=Palette.HABITAT, **kwargs,
        )

    @staticmethod
    def ordered(frame: pd.DataFrame, column: str, categories: Sequence[str]):
        """Impose a meaningful ordering on a categorical column."""
        out = frame.copy()
        out[column] = pd.Categorical(out[column], categories=categories, ordered=True)
        return out.sort_values(column)


# ===========================================================================
# SECTION 5 — PAGE REGISTRY
# ===========================================================================

PageRenderer = Callable[[QueryScope, int], None]
PAGE_REGISTRY: Dict[str, PageRenderer] = {}


def page(name: str) -> Callable[[PageRenderer], PageRenderer]:
    """Decorator that registers a renderer under its sidebar label."""

    def register(func: PageRenderer) -> PageRenderer:
        PAGE_REGISTRY[name] = func
        return func

    return register


# ===========================================================================
# SECTION 6 — PAGES
# ===========================================================================

@page("Overview")
def render_overview(scope: QueryScope, record_count: int) -> None:
    Theme.header("Bird Species Observation Analysis")
    st.markdown(
        "Distribution and diversity of bird species across **forest** and "
        "**grassland** habitats in eleven U.S. National Park units, "
        "May–July 2018."
    )

    # ---- Headline KPIs ----
    kpi_sql = f"""
        SELECT
            COUNT(*)                          AS Detections,
            COUNT(DISTINCT Scientific_Name)   AS Species,
            COUNT(DISTINCT Plot_Name)         AS Plots,
            COUNT(DISTINCT Admin_Unit_Code)   AS Parks,
            ROUND(AVG(Temperature), 1)        AS AvgTemp,
            ROUND(100.0 * SUM(PIF_Watchlist_Status) / COUNT(*), 2) AS WatchPct
        FROM observations
        {scope.where}
    """
    kpi = Database.query(kpi_sql, scope.params).iloc[0]

    for column, (label, value) in zip(
        st.columns(5, gap="small"),
        [
            ("Total detections", f"{int(kpi['Detections']):,}"),
            ("Distinct species", int(kpi["Species"])),
            ("Survey plots", int(kpi["Plots"])),
            ("Parks covered", int(kpi["Parks"])),
            ("On PIF Watchlist", f"{kpi['WatchPct']}%"),
        ],
    ):
        Theme.kpi(column, label, value)

    UI.sql(kpi_sql, scope.params)
    Theme.divider()

    # ---- Habitat comparison table ----
    st.subheader("Habitat comparison at a glance")

    habitat_sql = f"""
        SELECT
            Location_Type                     AS Habitat,
            COUNT(*)                          AS Detections,
            COUNT(DISTINCT Scientific_Name)   AS Species,
            COUNT(DISTINCT Plot_Name)         AS Plots,
            COUNT(DISTINCT Admin_Unit_Code)   AS Parks,
            ROUND(AVG(Temperature), 1)        AS AvgTempC,
            ROUND(AVG(Humidity), 1)           AS AvgHumidityPct,
            ROUND(100.0 * SUM(PIF_Watchlist_Status) / COUNT(*), 2)
                                              AS WatchlistPct,
            ROUND(100.0 * SUM(Flyover_Observed) / COUNT(*), 2)
                                              AS FlyoverPct
        FROM observations
        {scope.where}
        GROUP BY Location_Type
    """
    habitat = Database.query(habitat_sql, scope.params)

    # Species-per-plot is the effort-adjusted metric — the headline of the study
    per_plot_sql = f"""
        SELECT Location_Type, ROUND(AVG(sp), 1) AS SpeciesPerPlot
        FROM (
            SELECT Location_Type, Plot_Name,
                   COUNT(DISTINCT Scientific_Name) AS sp
            FROM observations
            {scope.where}
            GROUP BY Location_Type, Plot_Name
        )
        GROUP BY Location_Type
    """
    per_plot = Database.query(per_plot_sql, scope.params)
    habitat = habitat.merge(
        per_plot, left_on="Habitat", right_on="Location_Type", how="left"
    ).drop(columns=["Location_Type"])

    st.dataframe(habitat, use_container_width=True, hide_index=True)
    UI.note(
        "**Species** and **SpeciesPerPlot** tell different stories. Raw species "
        "totals are near-identical, but grassland achieves them from far fewer "
        "plots - the effort-adjusted figure is the fair comparison."
    )
    UI.sql(per_plot_sql, scope.params)

    Theme.divider()

    # ---- Two summary charts side by side ----
    left, right = st.columns(2)

    with left:
        st.subheader("Detections by park and habitat")
        park_sql = f"""
            SELECT Admin_Unit_Code AS Park, Location_Type AS Habitat,
                   COUNT(*) AS Detections
            FROM observations
            {scope.where}
            GROUP BY Admin_Unit_Code, Location_Type
            ORDER BY Detections DESC
        """
        parks = Database.query(park_sql, scope.params)
        fig = UI.by_habitat(parks, "Park", "Detections", text="Detections")
        UI.render(UI.labelled(fig, size=9), xaxis_title="Park code")
        UI.note(
            "Grassland habitat exists in only four of the eleven parks - "
            "ANTI, HAFE, MANA and MONO. That scarcity underpins the whole "
            "conservation argument."
        )

    with right:
        st.subheader("Monthly trend by habitat")
        month_sql = f"""
            SELECT Month_Name AS Month, Month AS MonthNum,
                   Location_Type AS Habitat, COUNT(*) AS Detections
            FROM observations
            {scope.where}
            GROUP BY Month_Name, Month, Location_Type
            ORDER BY MonthNum
        """
        months = Database.query(month_sql, scope.params)
        fig = px.line(
            months, x="Month", y="Detections", color="Habitat",
            markers=True, color_discrete_map=Palette.HABITAT,
        )
        fig.update_traces(line_width=3, marker_size=11)
        UI.render(fig)
        UI.note(
            "The two habitats run **opposite** seasonal cycles. Forest peaks "
            "in June; grassland dips in June and peaks in May and July. Any "
            "single-month comparison would be badly biased."
        )

    Theme.divider()
    st.subheader("Key findings")

    findings = [
        (
            st.info,
            "**Grassland is richer per unit area.**\n\n"
            "18.2 species per plot against forest's 13.3 — about 37% higher — "
            "from half the plots and a third of the parks.",
        ),
        (
            st.warning,
            "**But forest shelters the at-risk species.**\n\n"
            "Forest carries roughly 8x the PIF Watchlist detection rate "
            "(3.96% vs 0.47%), driven largely by the Wood Thrush.",
        ),
        (
            st.success,
            "**The habitats are complements, not competitors.**\n\n"
            "88 species use both, 20 are forest-exclusive and 19 "
            "grassland-exclusive. Neither can be sacrificed without loss.",
        ),
    ]
    for column, (callout, text) in zip(st.columns(3), findings):
        with column:
            callout(text)


@page("Spatial Analysis")
def render_spatial_analysis(scope: QueryScope, record_count: int) -> None:
    Theme.header("Spatial Analysis")
    st.markdown(
        "Where biodiversity concentrates across parks and individual survey "
        "plots — the basis for identifying protection priorities."
    )

    st.subheader("Biodiversity hotspots — plots ranked by species richness")

    top_n = st.slider("Number of plots to display", 5, 40, 15, step=5)

    hotspot_sql = f"""
        SELECT
            Plot_Name                        AS Plot,
            Location_Type                    AS Habitat,
            Admin_Unit_Code                  AS Park,
            COUNT(DISTINCT Scientific_Name)  AS SpeciesRichness,
            COUNT(*)                         AS Detections
        FROM observations
        {scope.where}
        GROUP BY Plot_Name, Location_Type, Admin_Unit_Code
        ORDER BY SpeciesRichness DESC
        LIMIT ?
    """
    hotspot_params = scope.bind(top_n)
    hotspots = Database.query(hotspot_sql, hotspot_params)

    fig = px.bar(
        hotspots.sort_values("SpeciesRichness"),
        x="SpeciesRichness", y="Plot", color="Habitat",
        orientation="h", color_discrete_map=Palette.HABITAT,
        text="SpeciesRichness", hover_data=["Park", "Detections"],
    )
    UI.render(
        UI.labelled(fig),
        height=max(420, top_n * 26),
        xaxis_title="Distinct species",
    )

    split = hotspots["Habitat"].value_counts()
    UI.note(
        f"Of these top {top_n} plots, "
        + " and ".join(f"**{v} are {k}**" for k, v in split.items())
        + ". Grassland is only about a third of all plots surveyed, so this is "
        "a marked over-representation."
    )
    UI.sql(hotspot_sql, hotspot_params)

    Theme.divider()
    st.subheader("Species richness per park")

    richness_sql = f"""
        SELECT Admin_Unit_Code AS Park, Location_Type AS Habitat,
               COUNT(DISTINCT Scientific_Name) AS Species,
               COUNT(DISTINCT Plot_Name)       AS Plots
        FROM observations
        {scope.where}
        GROUP BY Admin_Unit_Code, Location_Type
        ORDER BY Species DESC
    """
    richness = Database.query(richness_sql, scope.params)
    richness["Park Name"] = richness["Park"].map(ParkRegistry.label)

    chart_col, table_col = st.columns([3, 2])
    with chart_col:
        fig = UI.by_habitat(
            richness, "Park", "Species",
            text="Species", hover_data=["Park Name", "Plots"],
        )
        UI.render(UI.labelled(fig), height=430)
    with table_col:
        st.dataframe(
            richness[["Park", "Park Name", "Habitat", "Species", "Plots"]],
            use_container_width=True, hide_index=True, height=430,
        )

    UI.note(
        "MONO, ANTI and MANA post high grassland species counts from a small "
        "number of parks, while forest richness spreads thinly across all "
        "eleven units."
    )

    Theme.divider()
    st.subheader("Detections vs richness at plot level")

    scatter_sql = f"""
        SELECT Plot_Name AS Plot, Location_Type AS Habitat,
               Admin_Unit_Code AS Park,
               COUNT(*) AS Detections,
               COUNT(DISTINCT Scientific_Name) AS Species,
               ROUND(AVG(Temperature), 1) AS AvgTemp
        FROM observations
        {scope.where}
        GROUP BY Plot_Name, Location_Type, Admin_Unit_Code
    """
    scatter = Database.query(scatter_sql, scope.params)

    fig = px.scatter(
        scatter, x="Detections", y="Species", color="Habitat",
        size="Detections", hover_name="Plot",
        hover_data=["Park", "AvgTemp"],
        color_discrete_map=Palette.HABITAT, opacity=0.65,
    )
    UI.render(
        fig, height=480,
        xaxis_title="Total detections at plot",
        yaxis_title="Distinct species at plot",
    )
    UI.note(
        "The grassland cloud sits **above** the forest cloud: grassland plots "
        "reach higher richness even at comparable detection volumes, so the "
        "advantage is not merely a result of more birds being counted."
    )


@page("Temporal Analysis")
def render_temporal_analysis(scope: QueryScope, record_count: int) -> None:
    Theme.header("Temporal Analysis")
    st.markdown(
        "When birds are active — across the season, the week, and the morning. "
        "All records fall in a single 2018 breeding season (7 May – 19 July), "
        "so analysis is framed at month, week and hour level rather than "
        "year-over-year."
    )

    st.subheader("Detections by hour of survey commencement")

    hour_sql = f"""
        SELECT Start_Hour AS Hour, Location_Type AS Habitat,
               COUNT(*) AS Detections,
               COUNT(DISTINCT Scientific_Name) AS Species
        FROM observations
        {scope.where} AND Start_Hour IS NOT NULL
        GROUP BY Start_Hour, Location_Type
        ORDER BY Start_Hour
    """
    hours = Database.query(hour_sql, scope.params)

    fig = UI.by_habitat(hours, "Hour", "Detections", hover_data=["Species"])
    UI.render(fig, height=430, xaxis_title="Survey start hour (24-hour clock)")

    totals = hours.groupby("Hour")["Detections"].sum()
    peak_share = (
        totals.reindex([6, 7]).sum() / totals.sum() * 100 if totals.sum() else 0
    )
    UI.note(
        f"Surveys starting at 06:00–07:59 produce **{peak_share:.1f}%** of all "
        "detections in this selection. Yield collapses steeply after 09:00 — "
        "a 10:00 survey returns roughly a quarter of a 07:00 survey for the "
        "same staff cost."
    )
    UI.sql(hour_sql, scope.params)

    Theme.divider()

    weekly_col, visit_col = st.columns(2)

    with weekly_col:
        st.subheader("Weekly progression")
        week_sql = f"""
            SELECT Week, Location_Type AS Habitat, COUNT(*) AS Detections
            FROM observations
            {scope.where}
            GROUP BY Week, Location_Type
            ORDER BY Week
        """
        weeks = Database.query(week_sql, scope.params)
        fig = px.line(
            weeks, x="Week", y="Detections", color="Habitat",
            markers=True, color_discrete_map=Palette.HABITAT,
        )
        UI.render(fig, height=400, xaxis_title="ISO week number")
        UI.note(
            "Week-level resolution shows the seasonal handover more finely "
            "than the monthly view."
        )

    with visit_col:
        st.subheader("Repeat-visit yield")
        visit_sql = f"""
            SELECT Visit, Location_Type AS Habitat,
                   COUNT(DISTINCT Scientific_Name) AS Species,
                   COUNT(*) AS Detections
            FROM observations
            {scope.where}
            GROUP BY Visit, Location_Type
            ORDER BY Visit
        """
        visits = Database.query(visit_sql, scope.params)
        fig = UI.by_habitat(
            visits, "Visit", "Species",
            text="Species", hover_data=["Detections"],
        )
        UI.render(
            UI.labelled(fig), height=400, xaxis_title="Visit number to the plot"
        )
        UI.note(
            "Each repeat visit still finds a substantial community, with "
            "diminishing incremental returns. Single-visit surveys would "
            "systematically understate richness."
        )

    Theme.divider()
    st.subheader("Season × habitat heatmap")

    heat_sql = f"""
        SELECT Month_Name AS Month, Month AS MonthNum,
               Admin_Unit_Code AS Park, COUNT(*) AS Detections
        FROM observations
        {scope.where}
        GROUP BY Month_Name, Month, Admin_Unit_Code
        ORDER BY MonthNum
    """
    heat = Database.query(heat_sql, scope.params)
    if not heat.empty:
        pivot = heat.pivot(index="Park", columns="Month", values="Detections")
        pivot = pivot.reindex(
            columns=[m for m in Ordering.MONTH if m in pivot.columns]
        ).fillna(0)
        fig = px.imshow(
            pivot, text_auto=".0f", aspect="auto",
            color_continuous_scale="YlGnBu",
            labels={"color": "Detections"},
        )
        UI.render(fig, height=460)
        UI.note(
            "Reading across a row shows each park's seasonal rhythm. Parks "
            "with grassland peak early and late; forest-only parks peak in "
            "the middle of the season."
        )


@page("Species Analysis")
def render_species_analysis(scope: QueryScope, record_count: int) -> None:
    Theme.header("Species Analysis")
    st.markdown(
        "Which species are present, how diversity divides between habitats, "
        "and what the sex and detection data can and cannot tell us."
    )

    st.subheader("Most frequently detected species")

    n_species = st.slider("Number of species", 5, 30, 15, step=5)

    top_sql = f"""
        SELECT Common_Name AS Species, Scientific_Name AS ScientificName,
               COUNT(*) AS Detections,
               COUNT(DISTINCT Plot_Name) AS PlotsPresent,
               MAX(PIF_Watchlist_Status) AS OnWatchlist
        FROM observations
        {scope.where}
        GROUP BY Common_Name, Scientific_Name
        ORDER BY Detections DESC
        LIMIT ?
    """
    top_params = scope.bind(n_species)
    top = Database.query(top_sql, top_params)
    top["Status"] = top["OnWatchlist"].map({1: "PIF Watchlist", 0: "Not listed"})

    fig = px.bar(
        top.sort_values("Detections"),
        x="Detections", y="Species", orientation="h",
        color="Status", color_discrete_map=Palette.WATCHLIST,
        text="Detections", hover_data=["ScientificName", "PlotsPresent"],
    )
    UI.render(UI.labelled(fig), height=max(430, n_species * 26))
    UI.note(
        "The community is dominated by adaptable generalists. Note the "
        "**European Starling**, an invasive non-native that competes for the "
        "nest cavities native species depend on — high total bird numbers can "
        "mask declining community quality."
    )
    UI.sql(top_sql, top_params)

    Theme.divider()
    st.subheader("Habitat exclusivity — which species depend on only one habitat")

    exclusivity_sql = f"""
        SELECT
            Scientific_Name AS Species,
            Common_Name     AS CommonName,
            SUM(CASE WHEN Location_Type = 'Forest'    THEN 1 ELSE 0 END) AS ForestObs,
            SUM(CASE WHEN Location_Type = 'Grassland' THEN 1 ELSE 0 END) AS GrasslandObs
        FROM observations
        {scope.where}
        GROUP BY Scientific_Name, Common_Name
    """
    exclusivity = Database.query(exclusivity_sql, scope.params)

    if not exclusivity.empty:
        forest_only = exclusivity[
            (exclusivity.ForestObs > 0) & (exclusivity.GrasslandObs == 0)
        ]
        grass_only = exclusivity[
            (exclusivity.GrasslandObs > 0) & (exclusivity.ForestObs == 0)
        ]
        shared = exclusivity[
            (exclusivity.ForestObs > 0) & (exclusivity.GrasslandObs > 0)
        ]

        counts = [len(forest_only), len(shared), len(grass_only)]
        labels = ["Forest only", "Shared by both", "Grassland only"]
        metric_labels = [
            "Forest-exclusive species",
            "Shared by both habitats",
            "Grassland-exclusive species",
        ]
        for column, label, value in zip(st.columns(3), metric_labels, counts):
            Theme.kpi(column, label, value)

        fig = go.Figure(
            go.Bar(
                x=labels,
                y=counts,
                marker_color=[
                    Palette.HABITAT["Forest"], Palette.NEUTRAL,
                    Palette.HABITAT["Grassland"],
                ],
                text=counts,
                textposition="outside",
            )
        )
        UI.render(
            fig, height=400, yaxis_title="Distinct species",
            title="Habitat exclusivity of the species pool",
        )
        UI.note(
            "Roughly a third of the species pool uses only one habitat. These "
            "birds would **not relocate** if their habitat were converted — "
            "they would be lost from the network."
        )

        forest_tab, grass_tab = st.tabs(
            ["Forest-exclusive species", "Grassland-exclusive species"]
        )
        with forest_tab:
            st.dataframe(
                forest_only[["CommonName", "Species", "ForestObs"]]
                .sort_values("ForestObs", ascending=False),
                use_container_width=True, hide_index=True,
            )
        with grass_tab:
            st.dataframe(
                grass_only[["CommonName", "Species", "GrasslandObs"]]
                .sort_values("GrasslandObs", ascending=False),
                use_container_width=True, hide_index=True,
            )

    Theme.divider()

    sex_col, method_col = st.columns(2)

    with sex_col:
        st.subheader("Sex ratio")
        sex_sql = f"""
            SELECT Sex, COUNT(*) AS Detections
            FROM observations
            {scope.where}
            GROUP BY Sex
            ORDER BY Detections DESC
        """
        sexes = Database.query(sex_sql, scope.params)
        fig = px.pie(
            sexes, names="Sex", values="Detections", hole=0.35,
            color_discrete_sequence=Palette.SEX,
        )
        UI.render(fig, height=400)

        male = int(sexes.loc[sexes.Sex == "Male", "Detections"].sum())
        female = int(sexes.loc[sexes.Sex == "Female", "Detections"].sum())
        ratio = f"{male / female:.1f} : 1" if female else "n/a"
        st.error(
            f"**Observed male-to-female ratio: {ratio}.** The true biological "
            "ratio in most songbirds is close to 1:1. This is a **detection "
            "artefact**, not biology — most detections are acoustic and in "
            "most species only the male sings."
        )

    with method_col:
        st.subheader("Identification method")
        method_sql = f"""
            SELECT ID_Method AS Method, Location_Type AS Habitat,
                   COUNT(*) AS Detections
            FROM observations
            {scope.where}
            GROUP BY ID_Method, Location_Type
        """
        methods = Database.query(method_sql, scope.params)
        UI.render(UI.by_habitat(methods, "Method", "Detections"), height=400)

        acoustic = methods[
            methods.Method.isin(["Singing", "Calling"])
        ]["Detections"].sum()
        total_methods = methods["Detections"].sum()
        pct = acoustic / total_methods * 100 if total_methods else 0
        st.info(
            f"**{pct:.1f}% of detections are made by ear**, not by eye. Survey "
            "quality depends on the surveyor's auditory skill far more than on "
            "their optics — and it opens the door to automated acoustic "
            "recorders as a low-cost way to expand coverage."
        )


@page("Environmental Conditions")
def render_environmental_conditions(scope: QueryScope, record_count: int) -> None:
    Theme.header("Environmental Conditions")
    st.markdown(
        "How temperature, humidity, sky conditions and disturbance relate to "
        "bird detections — and what they reveal about habitat microclimate."
    )

    st.subheader("Microclimate: temperature and humidity by habitat")

    env_sql = f"""
        SELECT Location_Type AS Habitat, Temperature, Humidity
        FROM observations
        {scope.where} AND Temperature IS NOT NULL AND Humidity IS NOT NULL
    """
    env = Database.query(env_sql, scope.params)

    box_specs = [
        ("Temperature", "Temperature (°C)", "Temperature distribution"),
        ("Humidity", "Relative humidity (%)", "Humidity distribution"),
    ]
    for column, (metric, axis_title, title) in zip(st.columns(2), box_specs):
        with column:
            fig = px.box(
                env, x="Habitat", y=metric, color="Habitat",
                color_discrete_map=Palette.HABITAT, points=False,
            )
            UI.render(
                fig, height=420, showlegend=False,
                yaxis_title=axis_title, title=title,
            )

    stats = env.groupby("Habitat")[["Temperature", "Humidity"]].agg(
        ["mean", "std", "min", "max"]
    ).round(2)
    st.dataframe(stats, use_container_width=True)

    UI.note(
        "The forest canopy acts as a **climate buffer** — cooler, more humid, "
        "and far more stable. Grassland is hotter, drier and much more "
        "variable. This gives forest a conservation value that a species count "
        "alone misses: thermal refuge under a warming climate."
    )
    UI.sql(env_sql, scope.params)

    Theme.divider()
    st.subheader("Detections across temperature and humidity bands")

    band_specs = [
        ("Temp_Band", "By temperature band"),
        ("Humidity_Band", "By humidity band"),
    ]
    for column, (band_column, title) in zip(st.columns(2), band_specs):
        with column:
            band_sql = f"""
                SELECT {band_column} AS Band, Location_Type AS Habitat,
                       COUNT(*) AS Detections
                FROM observations
                {scope.where} AND {band_column} IS NOT NULL
                                AND {band_column} != 'nan'
                GROUP BY {band_column}, Location_Type
            """
            bands = Database.query(band_sql, scope.params)
            fig = UI.by_habitat(bands, "Band", "Detections", title=title)
            UI.render(fig, height=400)

    Theme.divider()
    st.subheader("Sky conditions and disturbance")

    sky_col, disturbance_col = st.columns(2)

    with sky_col:
        sky_sql = f"""
            SELECT Sky, Location_Type AS Habitat, COUNT(*) AS Detections
            FROM observations
            {scope.where}
            GROUP BY Sky, Location_Type
            ORDER BY Detections DESC
        """
        sky = Database.query(sky_sql, scope.params)
        fig = UI.by_habitat(sky, "Sky", "Detections", title="Sky condition")
        UI.render(fig, height=430, xaxis_tickangle=-25)

    with disturbance_col:
        disturbance_sql = f"""
            SELECT Disturbance, Location_Type AS Habitat, COUNT(*) AS Detections
            FROM observations
            {scope.where}
            GROUP BY Disturbance, Location_Type
        """
        disturbance = UI.ordered(
            Database.query(disturbance_sql, scope.params),
            "Disturbance", Ordering.DISTURBANCE,
        )
        fig = UI.by_habitat(
            disturbance, "Disturbance", "Detections",
            title="Reported disturbance severity",
        )
        UI.render(fig, height=430, xaxis_tickangle=-25)

    pct_disturbed = Database.scalar(
        f"""SELECT
                ROUND(100.0 * SUM(CASE WHEN Disturbance != 'No effect on count'
                                       THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct
            FROM observations {scope.where}""",
        scope.params,
    )

    st.warning(
        f"**{pct_disturbed}% of records in this selection carry some level of "
        "reported disturbance.** In a survey that is over 80% acoustic, noise "
        "directly suppresses detection — so abundance figures are systematically "
        "underestimated, and unevenly so. A plot beside a road may rank low "
        "because of traffic rather than because of its ecology. Hotspot "
        "rankings should be cross-checked against plot-level disturbance "
        "before they drive funding decisions."
    )


@page("Behaviour & Detection")
def render_behaviour_detection(scope: QueryScope, record_count: int) -> None:
    Theme.header("Behaviour & Detection")
    st.markdown(
        "Distance bands, flyover behaviour and how detection decays across the "
        "ten-minute point count."
    )

    st.subheader("Detection decay across the point count")

    interval_sql = f"""
        SELECT Interval_Length AS Interval, Location_Type AS Habitat,
               COUNT(*) AS Detections
        FROM observations
        {scope.where}
        GROUP BY Interval_Length, Location_Type
    """
    intervals = UI.ordered(
        Database.query(interval_sql, scope.params), "Interval", Ordering.INTERVAL
    )

    fig = UI.by_habitat(intervals, "Interval", "Detections", text="Detections")
    UI.render(
        UI.labelled(fig), height=430, xaxis_title="Time window within the count"
    )

    interval_totals = intervals.groupby("Interval", observed=True)["Detections"].sum()
    if interval_totals.sum():
        first = interval_totals.iloc[0] / interval_totals.sum() * 100
        first_five = interval_totals.iloc[:2].sum() / interval_totals.sum() * 100
        UI.note(
            f"The first 2.5 minutes capture **{first:.1f}%** of detections and "
            f"the first 5 minutes **{first_five:.1f}%**. Half of every survey's "
            "field time yields under a third of its data — but the later "
            "intervals disproportionately catch shy, quiet specialists, which "
            "are often the species of greatest conservation concern."
        )
    UI.sql(interval_sql, scope.params)

    Theme.divider()

    distance_col, flyover_col = st.columns(2)

    with distance_col:
        st.subheader("Detection distance")
        distance_sql = f"""
            SELECT Distance, Location_Type AS Habitat, COUNT(*) AS Detections
            FROM observations
            {scope.where}
            GROUP BY Distance, Location_Type
        """
        distances = Database.query(distance_sql, scope.params)
        fig = px.bar(
            distances, x="Habitat", y="Detections", color="Distance",
            barmode="stack", color_discrete_sequence=Palette.DISTANCE,
        )
        UI.render(fig, height=420)
        UI.note(
            "Dense forest vegetation limits both sightlines and sound, pulling "
            "detections closer to the observer. Open grassland lets both carry "
            "further."
        )

    with flyover_col:
        st.subheader("Flyover behaviour")
        flyover_sql = f"""
            SELECT Location_Type AS Habitat,
                   ROUND(100.0 * SUM(Flyover_Observed) / COUNT(*), 2) AS FlyoverPct,
                   SUM(Flyover_Observed) AS Flyovers,
                   COUNT(*) AS Total
            FROM observations
            {scope.where}
            GROUP BY Location_Type
        """
        flyovers = Database.query(flyover_sql, scope.params)
        fig = px.bar(
            flyovers, x="Habitat", y="FlyoverPct", color="Habitat",
            color_discrete_map=Palette.HABITAT, text="FlyoverPct",
            hover_data=["Flyovers", "Total"],
        )
        UI.render(
            UI.labelled(fig, template="%{text}%"),
            height=420, showlegend=False,
            yaxis_title="% of detections that were flyovers",
        )
        UI.note(
            "A flyover bird is passing through the airspace, not using the "
            "habitat below. Use the **Exclude flyovers** filter in the sidebar "
            "to measure true habitat dependency."
        )

    st.info(
        "**A caveat on forest's low flyover rate.** It almost certainly does "
        "not mean forest birds do not fly overhead — it means the canopy "
        "prevents surveyors from seeing them. Aerial-foraging and canopy "
        "species are systematically under-recorded in forest, so forest's true "
        "richness is likely higher than this dataset reports."
    )


@page("Observer Trends")
def render_observer_trends(scope: QueryScope, record_count: int) -> None:
    Theme.header("Observer Trends")
    st.markdown(
        "Only three surveyors collected the entire dataset, which makes "
        "observer-bias testing both feasible and necessary."
    )

    observer_sql = f"""
        SELECT
            Observer,
            COUNT(*)                          AS Detections,
            COUNT(DISTINCT Scientific_Name)   AS UniqueSpecies,
            COUNT(DISTINCT Plot_Name)         AS PlotsCovered,
            ROUND(100.0 * SUM(CASE WHEN ID_Method = 'Singing' THEN 1 ELSE 0 END)
                  / COUNT(*), 1)              AS PctBySong,
            ROUND(100.0 * SUM(PIF_Watchlist_Status) / COUNT(*), 2)
                                              AS WatchlistPct
        FROM observations
        {scope.where}
        GROUP BY Observer
        ORDER BY UniqueSpecies DESC
    """
    observers = Database.query(observer_sql, scope.params)

    st.subheader("Observer performance comparison")
    st.dataframe(observers, use_container_width=True, hide_index=True)
    UI.sql(observer_sql, scope.params)

    bar_specs = [
        ("Detections", "Survey effort (total records)", None),
        ("UniqueSpecies", "Distinct species reported", "Unique species"),
    ]
    for column, (metric, title, axis_title) in zip(st.columns(2), bar_specs):
        with column:
            fig = px.bar(
                observers, x="Observer", y=metric, color="Observer",
                text=metric, color_discrete_sequence=Palette.QUALITATIVE,
            )
            layout = {"showlegend": False, "title": title}
            if axis_title:
                layout["yaxis_title"] = axis_title
            UI.render(UI.labelled(fig), height=420, **layout)

    if len(observers) > 1:
        spread = int(observers.UniqueSpecies.max() - observers.UniqueSpecies.min())
        pct = (observers.UniqueSpecies.max() / observers.UniqueSpecies.min() - 1) * 100
        st.error(
            f"**Observer bias detected: a {spread}-species spread "
            f"({pct:.0f}% difference) between the highest and lowest "
            "surveyor.** Effort was distributed evenly and all observers "
            "covered both habitats, so this most plausibly reflects "
            "differences in auditory identification skill.\n\n"
            "This is a direct threat to the plot rankings on the Spatial "
            "Analysis page — a plot could appear rich or poor simply because "
            "of who walked it. Observer assignment must be checked for balance "
            "before any ranking drives a funding decision."
        )

    Theme.divider()
    st.subheader("Observer coverage by habitat")

    coverage_sql = f"""
        SELECT Observer, Location_Type AS Habitat, COUNT(*) AS Detections
        FROM observations
        {scope.where}
        GROUP BY Observer, Location_Type
    """
    coverage = Database.query(coverage_sql, scope.params)
    fig = UI.by_habitat(coverage, "Observer", "Detections", text="Detections")
    UI.render(UI.labelled(fig), height=430)
    UI.note(
        "All three observers surveyed both habitats in similar proportions, so "
        "no observer is confounded with a single habitat type. That is what "
        "makes the species-count gap above interpretable as skill rather than "
        "as an artefact of assignment."
    )


@page("Conservation Insights")
def render_conservation_insights(scope: QueryScope, record_count: int) -> None:
    Theme.header("Conservation Insights")
    st.markdown(
        "PIF Watchlist and Regional Stewardship status — the analysis that "
        "determines where protection effort should actually go."
    )

    conservation_sql = f"""
        SELECT
            Location_Type AS Habitat,
            ROUND(100.0 * SUM(PIF_Watchlist_Status) / COUNT(*), 3) AS WatchlistPct,
            ROUND(100.0 * SUM(Regional_Stewardship_Status) / COUNT(*), 2)
                                                                   AS StewardshipPct,
            SUM(PIF_Watchlist_Status)                              AS WatchlistObs,
            COUNT(*)                                               AS Total
        FROM observations
        {scope.where}
        GROUP BY Location_Type
    """
    conservation = Database.query(conservation_sql, scope.params)

    status_specs = [
        (
            "WatchlistPct",
            "PIF Watchlist detection rate",
            "% of detections on the Watchlist",
            ["WatchlistObs", "Total"],
        ),
        (
            "StewardshipPct",
            "Regional Stewardship species rate",
            "% of detections with stewardship status",
            None,
        ),
    ]
    for column, (metric, title, axis_title, hover) in zip(
        st.columns(2), status_specs
    ):
        with column:
            fig = px.bar(
                conservation, x="Habitat", y=metric, color="Habitat",
                color_discrete_map=Palette.HABITAT, text=metric,
                hover_data=hover,
            )
            UI.render(
                UI.labelled(fig, template="%{text}%"),
                height=420, showlegend=False,
                title=title, yaxis_title=axis_title,
            )

    UI.sql(conservation_sql, scope.params)

    Theme.divider()
    st.subheader("Which species drive the Watchlist signal")

    watchlist_sql = f"""
        SELECT
            Common_Name     AS Species,
            Scientific_Name AS ScientificName,
            Location_Type   AS Habitat,
            COUNT(*)                  AS Detections,
            COUNT(DISTINCT Plot_Name) AS PlotsPresent
        FROM observations
        {scope.where} AND PIF_Watchlist_Status = 1
        GROUP BY Common_Name, Scientific_Name, Location_Type
        ORDER BY Detections DESC
    """
    watchlist = Database.query(watchlist_sql, scope.params)

    if watchlist.empty:
        st.info("No PIF Watchlist species match the current filter selection.")
    else:
        fig = px.bar(
            watchlist.sort_values("Detections"),
            x="Detections", y="Species", color="Habitat", orientation="h",
            color_discrete_map=Palette.HABITAT, text="Detections",
            hover_data=["ScientificName", "PlotsPresent"],
        )
        UI.render(UI.labelled(fig), height=max(400, len(watchlist) * 34))

        st.dataframe(watchlist, use_container_width=True, hide_index=True)

        # Flag the species that are too rare to monitor reliably
        rare = watchlist[watchlist.Detections <= 5]
        if not rare.empty:
            names = ", ".join(rare.Species.unique())
            st.error(
                f"**Monitoring blind spot.** {names} — each detected five times "
                "or fewer in this selection. At these sample sizes no "
                "statistical trend can be detected, and a local extinction "
                "would be indistinguishable from ordinary sampling noise. A "
                "general point-count programme cannot monitor birds this rare; "
                "targeted species-specific surveys are needed."
            )

    Theme.divider()
    st.subheader("The dual-track conclusion")

    conclusions = [
        (
            st.success,
            "**Protect grassland for richness and scarcity.**\n\n"
            "18.2 species per plot against forest's 13.3, and it exists in "
            "only four of eleven parks. Grassland also needs *active* "
            "management — mowing, burning or grazing outside the breeding "
            "window — because without it the habitat succeeds to woodland on "
            "its own.",
        ),
        (
            st.info,
            "**Protect forest for at-risk species and thermal refuge.**\n\n"
            "Roughly 8x the Watchlist rate and a higher stewardship share, "
            "plus a cool, humid, stable microclimate that becomes more "
            "valuable as the climate warms.",
        ),
    ]
    for column, (callout, text) in zip(st.columns(2), conclusions):
        with column:
            callout(text)

    st.warning(
        "**These are complementary objectives, not competing claims on one "
        "budget line.** Species richness and conservation urgency point in "
        "opposite directions here, and a recommendation built on either metric "
        "alone would be wrong."
    )


@page("SQL Explorer")
def render_sql_explorer(scope: QueryScope, record_count: int) -> None:
    Theme.header("SQL Explorer")
    st.markdown(
        "Query the SQLite database directly. Three tables are available: "
        "`observations` (fact table), `species_reference` and `plot_reference` "
        "(dimension tables)."
    )

    with st.expander("Database schema", expanded=True):
        for table, rows, columns in Database.schema_overview():
            st.markdown(f"**`{table}`** — {rows:,} rows")
            st.caption(", ".join(columns))

    Theme.divider()

    preset_name = st.selectbox("Load a preset query", list(SQLPresets.QUERIES))
    query = st.text_area(
        "SQL query", value=SQLPresets.QUERIES[preset_name].strip(), height=240,
        help="Read-only queries. SELECT statements only.",
    )

    if st.button("Run query", type="primary"):
        if not SQLPresets.is_read_only(query):
            st.error(
                "Only read-only SELECT queries are permitted in this explorer."
            )
            return

        result = Database.query(query)
        if result.empty:
            st.info("Query returned no rows.")
            return

        st.success(f"Returned {len(result):,} rows.")
        st.dataframe(result, use_container_width=True, hide_index=True)
        st.download_button(
            "Download results as CSV",
            result.to_csv(index=False).encode("utf-8"),
            file_name="query_results.csv",
            mime="text/csv",
        )


class SQLPresets:
    """Canned queries for the SQL Explorer, plus a read-only guard."""

    FORBIDDEN = ("drop", "delete", "update", "insert", "alter", "create")

    QUERIES = {
        "Habitat summary": """
SELECT
    Location_Type                    AS Habitat,
    COUNT(*)                         AS Detections,
    COUNT(DISTINCT Scientific_Name)  AS Species,
    COUNT(DISTINCT Plot_Name)        AS Plots,
    ROUND(AVG(Temperature), 2)       AS AvgTemp,
    ROUND(AVG(Humidity), 2)          AS AvgHumidity
FROM observations
GROUP BY Location_Type;
""",
        "Top 10 hotspot plots": """
SELECT
    Plot_Name,
    Location_Type                    AS Habitat,
    Admin_Unit_Code                  AS Park,
    COUNT(DISTINCT Scientific_Name)  AS SpeciesRichness,
    COUNT(*)                         AS Detections
FROM observations
GROUP BY Plot_Name, Location_Type, Admin_Unit_Code
ORDER BY SpeciesRichness DESC
LIMIT 10;
""",
        "PIF Watchlist species": """
SELECT
    Location_Type            AS Habitat,
    Common_Name              AS Species,
    COUNT(*)                 AS Detections,
    COUNT(DISTINCT Plot_Name) AS PlotsPresent
FROM observations
WHERE PIF_Watchlist_Status = 1
GROUP BY Location_Type, Common_Name
ORDER BY Detections DESC;
""",
        "Peak activity hour (with JOIN)": """
SELECT
    o.Start_Hour                     AS SurveyHour,
    p.Location_Type                  AS Habitat,
    COUNT(*)                         AS Detections,
    COUNT(DISTINCT o.Scientific_Name) AS SpeciesDetected
FROM observations o
INNER JOIN plot_reference p
    ON o.Plot_Name = p.Plot_Name
   AND o.Location_Type = p.Location_Type
WHERE o.Start_Hour IS NOT NULL
GROUP BY o.Start_Hour, p.Location_Type
ORDER BY o.Start_Hour;
""",
        "Observer comparison": """
SELECT
    Observer,
    COUNT(*)                         AS Detections,
    COUNT(DISTINCT Scientific_Name)  AS UniqueSpecies,
    COUNT(DISTINCT Plot_Name)        AS PlotsCovered,
    ROUND(100.0 * SUM(CASE WHEN ID_Method = 'Singing' THEN 1 ELSE 0 END)
          / COUNT(*), 1)             AS PctBySong
FROM observations
GROUP BY Observer
ORDER BY UniqueSpecies DESC;
""",
        "Habitat-exclusive species": """
SELECT
    Common_Name AS Species,
    SUM(CASE WHEN Location_Type = 'Forest'    THEN 1 ELSE 0 END) AS ForestObs,
    SUM(CASE WHEN Location_Type = 'Grassland' THEN 1 ELSE 0 END) AS GrasslandObs
FROM observations
GROUP BY Common_Name
HAVING ForestObs = 0 OR GrasslandObs = 0
ORDER BY (ForestObs + GrasslandObs) DESC;
""",
    }

    @classmethod
    def is_read_only(cls, query: str) -> bool:
        lowered = query.strip().lower()
        return not any(
            lowered.startswith(word) or f" {word} " in lowered
            for word in cls.FORBIDDEN
        )


# ===========================================================================
# SECTION 7 — APPLICATION SHELL
# ===========================================================================

class Dashboard:
    """Wires the sidebar, the filter state and the page registry together."""

    @staticmethod
    def configure() -> None:
        st.set_page_config(
            page_title=AppConfig.PAGE_TITLE,
            page_icon=AppConfig.PAGE_ICON,
            layout=AppConfig.LAYOUT,
            initial_sidebar_state=AppConfig.SIDEBAR_STATE,
        )
        Theme.inject()

    @staticmethod
    def _collect_filters() -> FilterState:
        options = Database.distinct_values()

        habitats = st.sidebar.multiselect(
            "Habitat type", options["habitats"], default=options["habitats"]
        )
        parks = st.sidebar.multiselect(
            "Park (administrative unit)", options["parks"], default=options["parks"]
        )
        months = st.sidebar.multiselect(
            "Month", options["months"], default=options["months"]
        )
        observers = st.sidebar.multiselect(
            "Observer", options["observers"], default=options["observers"]
        )

        st.sidebar.markdown("**Advanced**")
        watchlist_only = st.sidebar.checkbox(
            "PIF Watchlist species only",
            value=False,
            help="Restrict to species on the Partners in Flight Watchlist of at-risk birds.",
        )
        exclude_flyovers = st.sidebar.checkbox(
            "Exclude flyovers",
            value=False,
            help=(
                "A flyover bird is passing through the airspace, not using the habitat "
                "below. Grassland records 16.3% flyovers against Forest's 1.1%, so "
                "excluding them gives a truer measure of habitat dependency."
            ),
        )

        return FilterState(
            habitats=habitats,
            parks=parks,
            months=months,
            observers=observers,
            watchlist_only=watchlist_only,
            exclude_flyovers=exclude_flyovers,
        )

    @staticmethod
    def _sidebar() -> Tuple[str, QueryScope, int]:
        """Draw the sidebar and return (page name, query scope, record count)."""
        st.sidebar.markdown(
            f"""
            <div style='padding:4px 0 14px 0;'>
              <div style='display:flex;align-items:center;gap:10px;'>
                <div style='width:38px;height:38px;border-radius:10px;
                            background:linear-gradient(140deg,{Palette.ACCENT},#1b6f65);
                            display:flex;align-items:center;justify-content:center;
                            font-size:20px;'>🐦</div>
                <div style='line-height:1.15;'>
                  <div style='font-size:1.02rem;font-weight:700;
                              color:{Palette.TEXT};'>Bird Observation</div>
                  <div style='font-size:.72rem;letter-spacing:.16em;
                              text-transform:uppercase;color:{Palette.ACCENT};
                              font-weight:600;'>Analysis</div>
                </div>
              </div>
              <div style='margin-top:12px;font-size:.79rem;color:{Palette.MUTED};'>
                {AppConfig.SUBTITLE}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        selected_page = st.sidebar.radio(
            "Navigate to", list(PAGE_REGISTRY), label_visibility="collapsed"
        )

        st.sidebar.markdown("---")
        st.sidebar.subheader("Filters")

        scope = Dashboard._collect_filters().compile()

        # Guard against an empty selection producing confusing blank charts
        record_count = int(
            Database.scalar(
                f"SELECT COUNT(*) AS n FROM observations {scope.where}",
                scope.params,
            )
        )

        st.sidebar.markdown("---")
        st.sidebar.metric("Records in current selection", f"{record_count:,}")

        if record_count == 0:
            st.warning(
                "No records match the current filter combination. "
                "Widen the filters in the sidebar to continue."
            )
            st.stop()

        st.sidebar.markdown("---")
        st.sidebar.caption(AppConfig.DATA_CAPTION)

        return selected_page, scope, record_count

    @classmethod
    def run(cls) -> None:
        """Application entry point: build the sidebar, then render the page."""
        cls.configure()
        selected_page, scope, record_count = cls._sidebar()

        renderer = PAGE_REGISTRY.get(selected_page)
        if renderer is None:
            st.error(f"Unknown page: {selected_page}")
            return
        renderer(scope, record_count)


if __name__ == "__main__":
    Dashboard.run()