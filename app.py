"""
Green Chemistry Dashboard for Sustainable Reaction Analysis
Main Streamlit Application
"""

from __future__ import annotations

import base64
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

logger = logging.getLogger(__name__)

try:
    from data_parser import ORDDataParser
    from metrics_calculator import GreenMetricsCalculator
    from visualizations import GreenChemistryVisualizer
    from advanced_analytics import StatisticalAnalyzer, ExpertSystem, SensitivityAnalyzer
    from pdf_generator import PDFReportGenerator
    _IMPORTS_OK = True
except ImportError as e:
    _IMPORTS_OK, _IMPORT_ERROR = False, str(e)


# ── helpers ──────────────────────────────────────────────────

def _logo_b64(path: str) -> Optional[str]:
    try:
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
    except Exception:
        pass
    return None


def _fmt(v: Any, fs: str, d: str = "N/A") -> str:
    try:
        return d if v is None or pd.isna(v) else fs.format(float(v))
    except (TypeError, ValueError):
        return d


def _sf(v: Any, d: float = 0.0) -> float:
    try:
        if v is None or pd.isna(v):
            return d
        f = float(v)
        return f if np.isfinite(f) else d
    except (TypeError, ValueError):
        return d


def _smean(s: pd.Series, d: float = 0.0) -> float:
    try:
        if s is None or len(s) == 0:
            return d
        v = s.mean()
        return float(v) if pd.notna(v) and np.isfinite(v) else d
    except Exception:
        return d


def _sstd(s: pd.Series, d: float = 0.0) -> float:
    try:
        if s is None or len(s) == 0:
            return d
        v = s.std()
        return float(v) if pd.notna(v) and np.isfinite(v) else d
    except Exception:
        return d


def _pctile(series: pd.Series, value: float, higher_better: bool = True) -> Optional[float]:
    try:
        s = pd.to_numeric(series, errors="coerce").dropna()
        if len(s) == 0 or value is None or pd.isna(value):
            return None
        pct = float((s <= value).sum() if higher_better else (s >= value).sum()) / len(s) * 100
        return round(pct, 1)
    except Exception:
        return None


def _dfhash(df: pd.DataFrame) -> str:
    ysum = _sf(df['yield_percent'].sum() if 'yield_percent' in df.columns else 0)
    return f"{len(df)}_{hash(tuple(df.columns))}_{ysum}"


def _invalidate_exports(current_hash: str):
    """Clear stale PDF/DOCX when filters change."""
    if st.session_state.get('_export_hash') != current_hash:
        for k in ('pdf_data', 'docx_data'):
            st.session_state.pop(k, None)
        st.session_state['_export_hash'] = current_hash


# ── cached loaders ───────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def load_data() -> Optional[pd.DataFrame]:
    try:
        parser = ORDDataParser('data/ord_search_results.pb')
        df = parser.parse_dataset()
        if df is None or df.empty:
            return None
        return GreenMetricsCalculator(df).calculate_all_metrics()
    except Exception as e:
        logger.error(f"Data loading failed: {e}")
        return None


@st.cache_data(show_spinner=False)
def apply_filters(key: str, df: pd.DataFrame, ymin: float, ymax: float,
                  ef_max: float, cat: str) -> pd.DataFrame:
    try:
        out = df[(df['yield_percent'] >= ymin) & (df['yield_percent'] <= ymax)
                 & (df['e_factor'] <= ef_max)].copy()
    except Exception:
        out = df.copy()
    if cat != 'All':
        try:
            out = out[out['catalyst'] == cat]
        except Exception:
            pass
    return out


@st.cache_data(show_spinner=False)
def cached_catalyst_comparison(k, df):
    try: return StatisticalAnalyzer(df).compare_catalysts()
    except Exception: return None

@st.cache_data(show_spinner=False)
def cached_ci(k, df):
    try: return StatisticalAnalyzer(df).confidence_intervals()
    except Exception: return None

@st.cache_data(show_spinner=False)
def cached_best(k, df):
    try: return StatisticalAnalyzer(df).best_catalyst()
    except Exception: return None

@st.cache_data(show_spinner=False)
def cached_recommendation(k, df, priority):
    try: return ExpertSystem(df).get_recommendation(priority)
    except Exception: return None

@st.cache_data(show_spinner=False)
def cached_rules(k, df):
    try: return ExpertSystem(df).extract_rules()
    except Exception: return []

@st.cache_data(show_spinner=False)
def cached_corr(k, df):
    try: return SensitivityAnalyzer(df).correlation_analysis()
    except Exception: return pd.DataFrame(), pd.Series(dtype=float), pd.Series(dtype=float)

@st.cache_data(show_spinner=False)
def cached_importance(k, df):
    try: return SensitivityAnalyzer(df).catalyst_importance()
    except Exception: return {"variance_explained": 0.0, "interpretation": "N/A"}


# ── page config ──────────────────────────────────────────────

st.set_page_config(
    page_title="Green Chemistry Dashboard", page_icon="🌿",
    layout="wide", initial_sidebar_state="expanded",
)
st.markdown("""<style>
.main-header{font-size:2.5rem;color:#2ecc71;text-align:center;font-weight:bold;margin-bottom:1rem}
.metric-card{background:#f0f2f6;padding:1rem;border-radius:.5rem;border-left:4px solid #2ecc71}
</style>""", unsafe_allow_html=True)


# ── main ─────────────────────────────────────────────────────

def main():
    if not _IMPORTS_OK:
        st.error(f"Import error: {_IMPORT_ERROR}")
        return

    # header
    logo = _logo_b64("image/icon.png")
    if logo:
        st.markdown(
            f'<div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:.5rem">'
            f'<img src="data:image/png;base64,{logo}" style="height:65px;width:65px;transform:translateY(-8px)"/>'
            f'<div class="main-header">Green Chemistry Dashboard</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="main-header">Green Chemistry Dashboard</div>', unsafe_allow_html=True)

    st.markdown(
        "<p style='text-align:center;color:#7f8c8d;font-size:1.1rem'>"
        "Sustainable Reaction Analysis for Ni-Catalyzed Suzuki-Miyaura Cross-Coupling</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # load
    with st.spinner("Loading reaction data and calculating metrics..."):
        df = load_data()
    if df is None or df.empty:
        st.error("No data available. Check 'data/ord_search_results.pb'.")
        return
    st.success(f"Loaded {len(df)} reactions with complete sustainability metrics")

    # ── sidebar filters ──
    st.sidebar.header("Filter Options")

    ymin = _sf(df['yield_percent'].min() if 'yield_percent' in df.columns else 0)
    ymax = _sf(df['yield_percent'].max() if 'yield_percent' in df.columns else 100, 100)
    if ymin >= ymax:
        ymax = ymin + 1.0
    yield_range = st.sidebar.slider("Yield Range (%)", ymin, ymax, (ymin, ymax))

    try:
        cats = ['All'] + sorted(str(c) for c in df['catalyst'].dropna().unique())
    except Exception:
        cats = ['All']
    sel_cat = st.sidebar.selectbox("Select Catalyst", cats)

    ef_ceil = max(_sf(df['e_factor'].max() if 'e_factor' in df.columns else 500, 500), 1.0)
    max_ef = st.sidebar.number_input("Max E-Factor", 0.0, ef_ceil, min(500.0, ef_ceil), 50.0)

    hk = _dfhash(df)
    dff = apply_filters(hk, df, yield_range[0], yield_range[1], max_ef, sel_cat)
    st.sidebar.markdown(f"**Filtered Reactions:** {len(dff)} / {len(df)}")

    if dff.empty:
        st.warning("No reactions match filters. Adjust settings.")
        return

    fk = _dfhash(dff)
    _invalidate_exports(fk)

    try:
        viz = GreenChemistryVisualizer(dff)
    except Exception as e:
        st.error(f"Visualizer init failed: {e}")
        return

    # ── tabs ──
    t1, t2, t3, t4, t5, t6, t7, t8, t9 = st.tabs([
        "Overview", "Metrics Analysis", "Catalyst Comparison",
        "Environmental Impact", "Statistical Analysis",
        "Expert Recommendations", "Sensitivity Analysis",
        "Data & Export", "Custom Reaction Evaluation",
    ])

    # ── Tab 1: Overview ──
    with t1:
        st.header("Dashboard Overview")
        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Average Yield", f"{_smean(dff['yield_percent']):.1f}%",
                   delta=f"{_sstd(dff['yield_percent']):.1f}% std")

        rme_d = f"{_sf(dff['rme'].max()):.1f}% max" if 'rme' in dff.columns and dff['rme'].notna().any() else "N/A"
        c2.metric("Average RME", f"{_smean(dff.get('rme', pd.Series(dtype=float))):.1f}%", delta=rme_d)

        ef_d = f"{_sf(dff['e_factor'].min()):.1f} min" if 'e_factor' in dff.columns and dff['e_factor'].notna().any() else "N/A"
        c3.metric("Average E-Factor", f"{_smean(dff.get('e_factor', pd.Series(dtype=float))):.1f}",
                   delta=ef_d, delta_color="inverse")

        co2_d = f"{_sf(dff['co2_kg'].sum()):.1f} kg total" if 'co2_kg' in dff.columns and dff['co2_kg'].notna().any() else "N/A"
        c4.metric("Avg CO\u2082 Emissions", f"{_smean(dff.get('co2_kg', pd.Series(dtype=float))):.2f} kg", delta=co2_d)

        st.markdown("---")
        for title, fn in [("Yield Distribution", viz.plot_yield_distribution),
                          ("Top Reactions by Sustainability Score", viz.plot_sustainability_score)]:
            st.subheader(title)
            try:
                st.plotly_chart(fn(), use_container_width=True)
            except Exception as e:
                st.warning(f"{title} failed: {e}")

    # ── Tab 2: Metrics ──
    with t2:
        st.header("Green Chemistry Metrics Analysis")
        for title, fn in [("Metrics Comparison", viz.plot_metrics_comparison),
                          ("Yield vs Environmental Impact", viz.plot_yield_vs_efactor),
                          ("Metrics Correlation Matrix", viz.plot_all_metrics_heatmap)]:
            st.subheader(title)
            try:
                st.plotly_chart(fn(), use_container_width=True)
            except Exception as e:
                st.warning(f"{title} failed: {e}")

    # ── Tab 3: Catalyst ──
    with t3:
        st.header("Catalyst Performance Analysis")
        try:
            st.plotly_chart(viz.plot_catalyst_performance(), use_container_width=True)
        except Exception as e:
            st.warning(f"Plot failed: {e}")

        st.subheader("Detailed Catalyst Statistics")
        try:
            if 'catalyst' in dff.columns:
                agg: Dict[str, Any] = {'yield_percent': ['mean', 'max', 'count']}
                for c in ('rme', 'e_factor', 'co2_kg'):
                    if c in dff.columns:
                        agg[c] = 'mean'
                stats = dff.groupby('catalyst').agg(agg).round(2)
                stats.columns = ['_'.join(c).strip('_') if isinstance(c, tuple) else c for c in stats.columns]
                rn = {
                    'yield_percent_mean': 'Avg Yield', 'yield_percent_max': 'Max Yield',
                    'yield_percent_count': 'Count', 'rme_mean': 'Avg RME',
                    'e_factor_mean': 'Avg E-Factor', 'co2_kg_mean': 'Avg CO\u2082',
                }
                stats = stats.rename(columns={k: v for k, v in rn.items() if k in stats.columns})
                sc = 'Avg Yield' if 'Avg Yield' in stats.columns else stats.columns[0]
                st.dataframe(stats.sort_values(sc, ascending=False), use_container_width=True)
        except Exception as e:
            st.warning(f"Stats failed: {e}")

    # ── Tab 4: Environmental ──
    with t4:
        st.header("Environmental Impact Assessment")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("CO\u2082 Emissions Distribution")
            try:
                st.plotly_chart(viz.plot_co2_emissions(), use_container_width=True)
            except Exception as e:
                st.warning(f"Plot failed: {e}")
        with c2:
            st.subheader("E-Factor Distribution")
            try:
                if 'e_factor' in dff.columns:
                    st.plotly_chart(px.box(dff, y='e_factor', title='E-Factor Distribution',
                                          labels={'e_factor': 'E-Factor'}), use_container_width=True)
            except Exception as e:
                st.warning(f"Plot failed: {e}")

        st.subheader("Environmental Summary")
        rows = []
        if 'co2_kg' in dff.columns and dff['co2_kg'].notna().any():
            rows.append(('Total CO\u2082 Emissions', f"{dff['co2_kg'].sum():.2f} kg"))
        if 'e_factor' in dff.columns and dff['e_factor'].notna().any():
            rows += [('Average E-Factor', f"{dff['e_factor'].mean():.2f}"),
                     ('Best E-Factor', f"{dff['e_factor'].min():.2f}"),
                     ('Worst E-Factor', f"{dff['e_factor'].max():.2f}")]
        if 'energy_kwh' in dff.columns and dff['energy_kwh'].notna().any():
            rows.append(('Total Energy', f"{dff['energy_kwh'].sum():.2f} kWh"))
        if rows:
            st.table(pd.DataFrame(rows, columns=['Metric', 'Value']))
        else:
            st.warning("No environmental data")

    # ── Tab 5: Statistical ──
    with t5:
        st.header("Advanced Statistical Analysis")

        st.subheader("Catalyst Comparison (ANOVA)")
        with st.spinner("Running statistical tests..."):
            comp = cached_catalyst_comparison(fk, dff)

        if comp:
            c1, c2 = st.columns(2)
            c1.metric("F-Statistic", f"{comp.get('f_statistic', 0):.2f}")
            c2.metric("P-Value", f"{comp.get('p_value', 1):.4f}")
            if comp.get('significant'):
                st.success("Catalyst choice SIGNIFICANTLY affects yield (p < 0.05)")
            else:
                st.info("No statistically significant difference found")

            st.markdown("---")
            st.subheader("Pairwise Comparisons")
            pw = comp.get('pairwise')
            if pw is not None and isinstance(pw, pd.DataFrame) and not pw.empty:
                st.dataframe(pw, use_container_width=True)
            else:
                st.info("No pairwise data available")
        else:
            st.warning("Not enough data for comparison")

        st.markdown("---")
        st.subheader("Confidence Intervals")
        with st.spinner("Calculating confidence intervals..."):
            ci = cached_ci(fk, dff)

        req = {'Catalyst', 'N', 'Mean_Yield', 'CI_Lower', 'CI_Upper'}
        if ci is not None and isinstance(ci, pd.DataFrame) and not ci.empty and req.issubset(ci.columns):
            try:
                fig = go.Figure()
                for _, r in ci.iterrows():
                    lo, hi, mu = _sf(r['CI_Lower']), _sf(r['CI_Upper']), _sf(r['Mean_Yield'])
                    n, nm = int(r['N']), str(r['Catalyst'])
                    fig.add_trace(go.Scatter(
                        x=[lo, mu, hi], y=[nm] * 3, mode='markers+lines', showlegend=False,
                        marker=dict(size=[10, 15, 10], color=['lightblue', 'darkblue', 'lightblue']),
                        line=dict(color='gray', width=2),
                        hovertemplate=(f"<b>{nm}</b><br>Mean: {mu:.1f}%<br>"
                                       f"95% CI: [{lo:.1f}%, {hi:.1f}%]<br>n={n}<extra></extra>"),
                    ))
                fig.update_layout(yaxis_title='', height=max(400, len(ci) * 40),
                  yaxis=dict(tickfont=dict(color='black', size=11, family='Arial Black')),
                  xaxis=dict(tickfont=dict(color='black', size=11, family='Arial'),
                             title=dict(text='Yield (%)', font=dict(color='black', size=12, family='Arial'))))
                fig.add_trace(go.Scatter(
                                    x=[None], y=[None], mode='markers',
                    marker=dict(color='darkblue', size=10),
                    name='Dot = Average Yield', showlegend=True
                ))
                fig.add_trace(go.Scatter(
                    x=[None], y=[None], mode='lines',
                    line=dict(color='gray', width=2),
                    name='Wide bar = 95% Catalyst Yield', showlegend=True
                ))
                fig.update_layout(
                    margin=dict(l=300, r=20, t=40, b=40),  # Increased left margin for long Ni-catalyst names [cite: 304, 648]

                    xaxis=dict(
                        title="<b>Yield (%)</b>",                 # Clear axis labeling [cite: 304, 431]
                        range=[0, 100],                    # Eliminates impossible negative values [cite: 534]
                        showgrid=True, 
                        gridcolor='rgba(200, 200, 200, 0.3)', # Subtle grid for better readability [cite: 526]
                        dtick=20                           # Standard scientific intervals
                    ),
                    
                     yaxis=dict(
                        showgrid=False,                    # Removes horizontal clutter [cite: 526]
                        automargin=True                    # Ensures text never overlaps the data bars [cite: 526]
                    ),

                    legend=dict(
                        x=0.98, y=0.98,
                        xanchor='right', yanchor='top',
                        bgcolor='rgba(255, 255, 255, 0.8)', # Slight background to separate from grid [cite: 526]
                        bordercolor='black',
                        borderwidth=0.5,
                        font=dict(size=11, family="Times New Roman") # Academic font style
                    ),

                    plot_bgcolor='white',                  # Clean white background for PDF printing [cite: 526, 529]
                    font=dict(size=12, family="Times New Roman")
                )
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(ci.round(2), use_container_width=True)
            except Exception as e:
                st.warning(f"CI plot failed: {e}")
        else:
            st.warning("Not enough data for CI calculation")

        st.markdown("---")
        st.subheader("Statistical Best Catalyst")
        best = cached_best(fk, dff)
        if best:
            c1, c2, c3 = st.columns(3)
            c1.metric("Recommended", str(best.get('catalyst', '?')))
            c2.metric("Expected Yield", f"{_sf(best.get('mean_yield')):.1f}%")
            c3.metric("95% CI", f"{_sf(best.get('ci_lower')):.1f}% - {_sf(best.get('ci_upper')):.1f}%")
            st.info(f"Based on {best.get('n_reactions', 0)} reactions. "
                    f"True yield is 95% likely between "
                    f"{_sf(best.get('ci_lower')):.1f}% and {_sf(best.get('ci_upper')):.1f}%.")
        else:
            st.warning("Insufficient data")

    # ── Tab 6: Expert ──
    with t6:
        st.header("Expert System Recommendations")
        st.info("Analyzes patterns in data and provides recommendations based on learned rules")

        c1, c2 = st.columns([1, 2])
        with c1:
            priority = st.radio(
                "Priority",
                ['balanced', 'yield', 'sustainability'],
                format_func=lambda x: {'balanced': 'Balanced', 'yield': 'Max Yield',
                                        'sustainability': 'Min Waste'}.get(x, x),
            )

        with st.spinner("Generating recommendation..."):
            rec = cached_recommendation(fk, dff, priority)

        with c2:
            if rec:
                st.subheader(f"Recommendation: {rec.get('metric', 'N/A')}")
                st.markdown(
                    f"**Catalyst:** {rec.get('catalyst', '?')} | "
                    f"**Solvent:** {rec.get('solvent', '?')} | "
                    f"**Temp:** {_fmt(rec.get('temperature'), '{:.1f} C')}\n\n"
                    f"Yield: {_fmt(rec.get('yield'), '{:.1f}%')} | "
                    f"E-Factor: {_fmt(rec.get('e_factor'), '{:.1f}')} | "
                    f"RME: {_fmt(rec.get('rme'), '{:.1f}%')}\n\n"
                    f"*Based on reaction #{rec.get('reaction_id', '?')}*"
                )
            else:
                st.warning("No recommendation available")

        st.markdown("---")
        st.subheader("Knowledge Base (Learned Rules)")
        with st.spinner("Extracting rules..."):
            rules = cached_rules(fk, dff)

        for rtype, label, fn in [('BEST PRACTICE', 'Best Practices', st.success),
                                  ('AVOID', 'What to Avoid', st.error)]:
            subset = [r for r in rules if r.get('type') == rtype]
            if subset:
                fn(f"**{label}:**")
                for r in subset:
                    st.write(f"- {r['rule']} — Yield: {r['avg_yield']:.1f}%, "
                             f"E-Factor: {r['avg_efactor']:.1f} ({r['evidence']})")

        profiles = [r for r in rules if r.get('type') == 'PROFILE']
        if profiles:
            st.write("**Catalyst Profiles:**")
            for r in profiles:
                st.write(f"{r['rule']} — Yield: {r['avg_yield']:.1f}%, "
                         f"E-Factor: {r['avg_efactor']:.1f} ({r['evidence']})")

    # ── Tab 7: Sensitivity ──
    with t7:
        st.header("Sensitivity Analysis")
        st.info("Shows which factors most strongly affect reaction outcomes")

        st.subheader("Factor Impact on Yield")
        with st.spinner("Analyzing factor correlations..."):
            corr_matrix, yield_corr, ef_corr = cached_corr(fk, dff)

        try:
            if isinstance(yield_corr, pd.Series) and not yield_corr.empty:
                impact = yield_corr.drop('yield_percent', errors='ignore').dropna()
                if len(impact) > 0:
                    imp = impact.reindex(impact.abs().sort_values(ascending=True).index)
                    colors = ['#2ecc71' if v > 0 else '#e74c3c' for v in imp.values]
                    fig = go.Figure(go.Bar(
                        y=[m.replace('_', ' ').title() for m in imp.index], x=imp.values,
                        orientation='h',
                        marker=dict(color=colors, line=dict(width=1, color='white')),
                        hovertemplate='<b>%{y}</b><br>r = %{x:.3f}<extra></extra>',
                    ))
                    fig.add_vline(x=0, line_color="gray", line_width=1)
                    fig.add_vrect(x0=-0.3, x1=0.3, fillcolor="rgba(200,200,200,0.1)",
                                  line_width=0, annotation_text="Weak", annotation_position="top")
                    fig.update_layout(
                        title=dict(text='Factor Impact on Yield', x=0.5),
                        xaxis=dict(title='Correlation with Yield', range=[-1.05, 1.05]),
                        height=max(400, len(imp) * 45), template='plotly_white', showlegend=False,
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    st.caption("🟢 Green = Increases yield | 🔴 Red = Decreases yield | Longer bar = Stronger effect")
        except Exception as e:
            st.warning(f"Impact chart failed: {e}")

        st.markdown("---")
        c1, c2 = st.columns(2)
        for col, title, series, drop in [(c1, "What Increases Yield?", yield_corr, 'yield_percent'),
                                          (c2, "What Increases Waste?", ef_corr, 'e_factor')]:
            with col:
                st.subheader(title)
                if isinstance(series, pd.Series) and not series.empty:
                    for f, v in series.drop(drop, errors='ignore').head(3).items():
                        st.write(f"- **{f}**: {v:.3f} ({'increases' if v > 0 else 'decreases'})")
                else:
                    st.write("Not enough data")

        st.markdown("---")
        st.subheader("How Much Does Catalyst Choice Matter?")
        with st.spinner("Calculating catalyst importance..."):
            importance = cached_importance(fk, dff)
        ve = _sf(importance.get('variance_explained', 0))

        c1, c2 = st.columns([1, 2])
        c1.metric("Variance Explained", f"{ve:.1f}%")
        with c2:
            st.info(f"**Interpretation:** {importance.get('interpretation', 'N/A')}")
            if ve > 14:
                st.success("Catalyst selection is CRITICAL to success")
            elif ve > 6:
                st.warning("Catalyst matters, but other factors also important")
            else:
                st.error("Catalyst has minimal impact — focus on other conditions")

    # ── Tab 8: Data & Export ──
    with t8:
        st.header("Data Table & Export")

        all_cols = dff.columns.tolist()
        defaults = [c for c in ['reaction_id', 'catalyst', 'yield_percent',
                                 'atom_economy', 'rme', 'e_factor', 'co2_kg'] if c in all_cols]
        sel_cols = st.multiselect("Columns to display", all_cols, default=defaults)
        if sel_cols:
            sc = 'yield_percent' if 'yield_percent' in sel_cols else sel_cols[0]
            st.dataframe(dff[sel_cols].sort_values(sc, ascending=False),
                         use_container_width=True, height=350)

        st.markdown("---")
        st.subheader("Summary Statistics")
        try:
            st.dataframe(viz.create_summary_table(), use_container_width=True)
        except Exception as e:
            st.warning(f"Summary failed: {e}")

        st.markdown("---")
        st.subheader("Export Reports")
        c1, c2, c3 = st.columns(3)

        with c1:
            st.write("**CSV Data**")
            try:
                st.download_button(
                    "Download CSV", dff.to_csv(index=False).encode(),
                    f"green_chemistry_{datetime.now():%Y%m%d}.csv", "text/csv",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"CSV failed: {e}")

        with c2:
            st.write("**PDF Report**")
            _pdf = st.empty()
            if 'pdf_data' in st.session_state:
                _pdf.download_button(
                    "Download PDF Report", st.session_state['pdf_data'],
                    f"report_{datetime.now():%Y%m%d_%H%M%S}.pdf",
                    "application/pdf", use_container_width=True,
                )
            else:
                if _pdf.button("Download PDF Report", use_container_width=True):
                    with st.spinner("Generating PDF report..."):
                        try:
                            st.session_state['pdf_data'] = PDFReportGenerator(
                                df, dff, logo_path="image/icon.png"
                            ).generate_combined_pdf()
                        except Exception as e:
                            st.error(f"PDF generation failed: {e}")
                    if st.session_state.get('pdf_data'):
                        _pdf.download_button(
                            "Download PDF Report", st.session_state['pdf_data'],
                            f"report_{datetime.now():%Y%m%d_%H%M%S}.pdf",
                            "application/pdf", use_container_width=True,
                        )

        with c3:
            st.write("**Word Document**")
            _docx = st.empty()
            if 'docx_data' in st.session_state:
                _docx.download_button(
                    "Download DOCX Report", st.session_state['docx_data'],
                    f"report_{datetime.now():%Y%m%d_%H%M%S}.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
            else:
                if _docx.button("Download DOCX Report", use_container_width=True):
                    with st.spinner("Generating DOCX report..."):
                        try:
                            st.session_state['docx_data'] = PDFReportGenerator(
                                df, dff, logo_path="image/icon.png"
                            ).generate_full_report_docx()
                        except ImportError:
                            st.error("python-docx not installed. Run: pip install python-docx")
                        except Exception as e:
                            st.error(f"DOCX generation failed: {e}")
                    if st.session_state.get('docx_data'):
                        _docx.download_button(
                            "Download DOCX Report", st.session_state['docx_data'],
                            f"report_{datetime.now():%Y%m%d_%H%M%S}.docx",
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True,
                        )

    # ── Tab 9: Custom Reaction ──
    with t9:
        st.header("Custom Reaction Evaluator")
        st.info("Please enter hypothetical conditions manually and it is independent of dataset")

        solvents = ["dioxane", "thf", "toluene", "dmf", "water",
                     "ethanol", "methanol", "acetone", "ethyl acetate"]

        with st.form("custom_rxn"):
            cl, cr = st.columns(2)
            with cl:
                cat_in = st.text_input("Catalyst", "Ni catalyst (hypothetical)", disabled=True,
                                        help="Generic Ni catalyst (5 mol%, 300 g/mol).")
                sol_in = st.selectbox("Solvent", solvents)
                scale = st.number_input("Scale (mmol)", 0.1, 10.0, 1.0, 0.1)
            with cr:
                temp_in = st.number_input("Temperature (C)", 0.0, 200.0, 80.0, 1.0)
                time_in = st.number_input("Time (hours)", 0.1, 72.0, 12.0, 0.5)
                yield_in = st.slider("Yield (%)", 0.0, 100.0, 80.0, 1.0)
            submitted = st.form_submit_button("Calculate Green Metrics")

        if submitted:
            with st.spinner("Calculating metrics..."):
                try:
                    cdf = pd.DataFrame([{
                        "reaction_id": "user_custom", "catalyst": (cat_in or "").strip() or "Unknown",
                        "solvent": sol_in, "temperature_c": float(temp_in),
                        "reaction_time_h": float(time_in), "yield_percent": float(yield_in),
                    }])
                    res = GreenMetricsCalculator(cdf, reaction_scale_mmol=float(scale)) \
                        .calculate_all_metrics(show_progress=False)
                    r = res.iloc[0]

                    st.subheader("Calculated Green Metrics")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Yield", _fmt(r.get('yield_percent'), "{:.1f}%"))
                    m1.metric("Atom Economy", _fmt(r.get('atom_economy'), "{:.1f}%"))
                    m2.metric("RME", _fmt(r.get('rme'), "{:.1f}%"))
                    m2.metric("E-Factor", _fmt(r.get('e_factor'), "{:.2f}"))
                    m3.metric("Green Score", _fmt(r.get('green_score'), "{:.1f}"))
                    m3.metric("CO\u2082 Emissions", _fmt(r.get('co2_kg'), "{:.3f} kg"))

                    st.markdown("### Full breakdown")
                    dcols = [c for c in ["yield_percent", "atom_economy", "rme", "e_factor", "pmi",
                                          "carbon_efficiency", "solvent_score", "energy_kwh",
                                          "co2_kg", "green_score"] if c in res.columns]
                    st.dataframe(res[dcols].T.rename(columns={0: "Value"}))

                    st.markdown("### Dataset comparison")
                    bc = st.columns(3)
                    benchmarks = [
                        (bc[0], 'yield_percent', 'Yield', True),
                        (bc[1], 'e_factor', 'E-Factor (lower)', False),
                        (bc[2], 'green_score', 'Green score', True),
                    ]
                    for col, key, label, hb in benchmarks:
                        v = r.get(key)
                        if key in df.columns and v is not None and not pd.isna(v):
                            p = _pctile(df[key], float(v), hb)
                            if p is not None:
                                col.write(f"- {label} better than **{p:.1f}%** of reactions")

                except Exception as e:
                    st.error(f"Evaluation failed: {e}")

    # footer
    st.markdown("---")
    st.markdown(
        "<p style='text-align:center;color:#95a5a6'>"
        "Green Chemistry Dashboard | Data: Open Reaction Database</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()