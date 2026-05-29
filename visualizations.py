"""
Visualization Module for Green Chemistry Dashboard
Creates charts and graphs for sustainability metrics
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

import plotly.graph_objects as go
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


class GreenChemistryVisualizer:
    """Generate visualizations for green chemistry metrics. 7 essential graphs."""

    DEFAULT_COLORS: Dict[str, str] = {
        'primary': '#2ecc71', 'secondary': '#3498db', 'accent': '#e74c3c',
        'warning': '#f39c12', 'purple': '#9b59b6', 'teal': '#1abc9c',
        'neutral': '#7f8c8d',
    }

    CHART_PALETTE: List[str] = [
        '#2ecc71', '#3498db', '#e74c3c', '#f39c12', '#9b59b6',
        '#1abc9c', '#e67e22', '#34495e', '#16a085', '#c0392b',
        '#27ae60', '#2980b9', '#8e44ad', '#d35400', '#c0392b',
    ]

    def __init__(self, df: pd.DataFrame, colors: Optional[Dict[str, str]] = None):
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pd.DataFrame, got {type(df).__name__}")
        if len(df) == 0:
            raise ValueError("DataFrame cannot be empty")

        self.df = df.copy()
        self.colors = colors or self.DEFAULT_COLORS

        if 'yield_percent' not in self.df.columns:
            raise ValueError("Missing required column: yield_percent")

        self._prepare_data()
        logger.info(f"Visualizer initialized with {len(self.df)} reactions")

    def _prepare_data(self) -> None:
        """Prepare and clean data for visualization"""
        self.df = self.df.reset_index(drop=True)

        if 'reaction_id' in self.df.columns:
            self.df['reaction_id_short'] = self.df['reaction_id'].apply(
                lambda x: (
                    str(x)[:12] + '...'
                    if pd.notna(x) and len(str(x)) > 12
                    else str(x) if pd.notna(x) else 'Unknown'
                )
            )
        else:
            self.df['reaction_id_short'] = [f'Rxn_{i:03d}' for i in range(len(self.df))]

        if 'catalyst' in self.df.columns:
            self.df['catalyst_short'] = self.df['catalyst'].apply(
                lambda x: (
                    str(x)[:28] + '...'
                    if pd.notna(x) and len(str(x)) > 30
                    else str(x) if pd.notna(x) else 'Unknown'
                )
            )

        if 'solvent' in self.df.columns:
            self.df['solvent_clean'] = self.df['solvent'].apply(self._clean_solvent)

    @staticmethod
    def _clean_solvent(solvent: Any) -> str:
        """Remove duplicate solvents from string"""
        if pd.isna(solvent) or not solvent:
            return 'Unknown'
        seen: set = set()
        unique: List[str] = []
        for p in (s.strip() for s in str(solvent).split(';')):
            if p and p.lower() not in seen:
                unique.append(p)
                seen.add(p.lower())
        return '; '.join(unique) or 'Unknown'

    # ============================================================
    # SAFE DATA CONVERSION HELPERS
    # ============================================================

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        """Safely convert to float"""
        if value is None:
            return default
        try:
            if pd.isna(value):
                return default
            result = float(value)
            return default if (np.isnan(result) or np.isinf(result)) else result
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_list(series: pd.Series, default: float = 0.0) -> List[float]:
        """Convert Series to list of floats"""
        return [GreenChemistryVisualizer._safe_float(x, default) for x in series]

    @staticmethod
    def _to_str_list(series: pd.Series, default: str = 'Unknown') -> List[str]:
        """Convert Series to list of strings"""
        return [str(x) if pd.notna(x) else default for x in series]

    def _empty_figure(self, message: str = "No data available") -> go.Figure:
        """Create empty figure with message"""
        fig = go.Figure()
        fig.add_annotation(
            text=f"⚠️ {message}",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=18, color="gray"),
        )
        fig.update_layout(
            height=400, template='plotly_white',
            xaxis=dict(visible=False), yaxis=dict(visible=False),
        )
        return fig

    # ============================================================
    # STABLE DISPLAY METHOD
    # ============================================================

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Sanitize filename for cross-platform compatibility"""
        if not name:
            return 'figure'
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).rstrip('. ')
        return (name[:50] if name else 'figure') or 'figure'

    def show_figure(self, fig: go.Figure, name: str = "figure") -> bool:
        """Display figure using webbrowser (100% reliable)."""
        try:
            safe_name = self._sanitize_filename(name)
            temp_dir = os.path.join(tempfile.gettempdir(), 'green_chem_charts')
            os.makedirs(temp_dir, exist_ok=True)
            filepath = os.path.join(temp_dir, f'{safe_name}.html')

            fig.write_html(filepath, auto_open=False, include_plotlyjs='inline')

            if not os.path.exists(filepath):
                logger.error(f"Failed to create file: {filepath}")
                return False

            uri = Path(filepath).resolve().as_uri()
            opened = webbrowser.open(uri, new=2)

            if opened:
                logger.info(f"  ✓ Displayed: {name}")
                logger.info(f"     Location: {filepath}")
            else:
                logger.warning(f"  ⚠ Browser may not have opened: {name}")
                logger.info(f"     Open manually: {filepath}")

            return True

        except PermissionError:
            logger.error(f"  ✗ Permission denied writing {name}")
            return False
        except Exception as e:
            logger.error(f"  ✗ Failed to display {name}: {e}")
            return False

    # ============================================================
    # CHART 1: YIELD DISTRIBUTION
    # ============================================================

    def plot_yield_distribution(self, nbins: int = 20) -> go.Figure:
        """Plot distribution of reaction yields with mean and median lines"""
        logger.info("Creating yield distribution plot...")

        try:
            yield_data = self.df['yield_percent'].dropna()
            if len(yield_data) == 0:
                return self._empty_figure("No yield data")

            yield_list = self._to_list(yield_data)

            mean_val = float(np.mean(yield_list))
            median_val = float(np.median(yield_list))
            std_val = float(np.std(yield_list))
            min_val = float(min(yield_list))
            max_val = float(max(yield_list))

            fig = go.Figure()

            fig.add_trace(go.Histogram(
                x=yield_list, nbinsx=nbins,
                marker_color=self.colors['primary'], opacity=0.75,
                name='Yield Distribution',
                hovertemplate='Yield: %{x:.1f}%<br>Count: %{y}<extra></extra>',
            ))

            fig.add_vline(x=mean_val, line_dash="dash",
                          line_color=self.colors['accent'], line_width=2)

            mean_median_close = abs(mean_val - median_val) < (max_val - min_val) * 0.05
            mean_y = 1.08 if mean_median_close else 1.05

            fig.add_annotation(
                x=mean_val, y=mean_y, yref='paper',
                text=f"Mean: {mean_val:.1f}%", showarrow=False,
                font=dict(size=11, color=self.colors['accent']),
                xanchor='left' if mean_val < median_val else 'right',
            )

            fig.add_vline(x=median_val, line_dash="dot",
                          line_color=self.colors['secondary'], line_width=2)
            fig.add_annotation(
                x=median_val, y=0.95, yref='paper',
                text=f"Median: {median_val:.1f}%", showarrow=False,
                font=dict(size=11, color=self.colors['secondary']),
                xanchor='right' if mean_val < median_val else 'left',
            )

            fig.add_annotation(
                x=0.98, y=0.95, xref='paper', yref='paper',
                text=(f"<b>Statistics</b><br>N: {len(yield_list)}<br>"
                      f"Mean: {mean_val:.1f}%<br>Median: {median_val:.1f}%<br>"
                      f"Std Dev: {std_val:.1f}%<br>"
                      f"Range: {min_val:.1f}% - {max_val:.1f}%"),
                showarrow=False,
                font=dict(size=10, color='black'),
                align='left',
                bgcolor='white',
                bordercolor='gray',
                borderwidth=1,
                borderpad=6,
            )

            fig.update_layout(
                title=dict(text='Distribution of Reaction Yields', x=0.5),
                xaxis_title='Yield (%)', yaxis_title='Frequency',
                showlegend=False, height=480, template='plotly_white',
            )

            return fig

        except Exception as e:
            logger.error(f"Yield distribution error: {e}")
            return self._empty_figure(str(e))

    # ============================================================
    # CHART 2: METRICS COMPARISON
    # ============================================================

    def plot_metrics_comparison(self, top_n: int = 15) -> go.Figure:
        """Compare AE, RME, E-Factor for top reactions"""
        logger.info(f"Creating metrics comparison for top {top_n} reactions...")

        try:
            required = ['yield_percent', 'atom_economy', 'rme', 'e_factor']
            if not all(c in self.df.columns for c in required):
                return self._empty_figure("Missing required metrics")

            df_clean = self.df.dropna(subset=required).reset_index(drop=True)
            if len(df_clean) == 0:
                return self._empty_figure("No complete data")

            df_top = df_clean.nlargest(min(top_n, len(df_clean)), 'yield_percent')
            df_top = df_top.sort_values('yield_percent', ascending=True).reset_index(drop=True)

            ids = self._to_str_list(df_top['reaction_id_short'])

            fig = make_subplots(
                rows=1, cols=3,
                subplot_titles=['Atom Economy (%)', 'RME (%)', 'E-Factor'],
                horizontal_spacing=0.12,
            )

            for col_idx, (metric, color, fmt) in enumerate([
                ('atom_economy', 'lightblue', 'AE'),
                ('rme', 'lightgreen', 'RME'),
                ('e_factor', 'salmon', 'E-Factor'),
            ], 1):
                vals = self._to_list(df_top[metric])
                unit = '%' if metric != 'e_factor' else ''
                fig.add_trace(go.Bar(
                    y=ids, x=vals, orientation='h', marker_color=color,
                    hovertemplate=f'<b>%{{y}}</b><br>{fmt}: %{{x:.1f}}{unit}<extra></extra>',
                ), row=1, col=col_idx)

            fig.update_layout(
                title=dict(text=f'Green Chemistry Metrics (Top {len(df_top)} by Yield)', x=0.5),
                showlegend=False,
                height=max(450, len(df_top) * 28),
                template='plotly_white',
            )

            fig.update_xaxes(title_text='%', row=1, col=1)
            fig.update_xaxes(title_text='%', row=1, col=2)
            fig.update_xaxes(title_text='Waste/Product', row=1, col=3)

            return fig

        except Exception as e:
            logger.error(f"Metrics comparison error: {e}")
            return self._empty_figure(str(e))

    # ============================================================
    # CHART 3: YIELD VS E-FACTOR (FIXED: legend dark mode)
    # ============================================================

    def plot_yield_vs_efactor(self) -> go.Figure:
        """Scatter plot: Yield vs E-Factor with ideal zone"""
        logger.info("Creating yield vs E-factor scatter plot...")

        try:
            if 'yield_percent' not in self.df.columns or 'e_factor' not in self.df.columns:
                return self._empty_figure("Missing yield or E-factor")

            df_clean = self.df.dropna(subset=['yield_percent', 'e_factor']).reset_index(drop=True)
            if len(df_clean) == 0:
                return self._empty_figure("No valid data")

            x_data = self._to_list(df_clean['yield_percent'])
            y_data = self._to_list(df_clean['e_factor'])
            ids = self._to_str_list(df_clean['reaction_id_short'])

            catalysts = (self._to_str_list(df_clean['catalyst_short'])
                         if 'catalyst_short' in df_clean.columns
                         else ['Unknown'] * len(x_data))

            unique_cats = list(dict.fromkeys(catalysts))[:10]

            if 'rme' in df_clean.columns:
                rme_data = self._to_list(df_clean['rme'], default=10)
                max_rme = max(rme_data) if max(rme_data) > 0 else 1.0
                sizes = [max(8, (r / max_rme) * 35) for r in rme_data]
            else:
                sizes = [14] * len(x_data)

            hover_extras: Dict[str, List[float]] = {}
            for key, col in [('AE', 'atom_economy'), ('RME', 'rme'), ('Score', 'green_score')]:
                if col in df_clean.columns:
                    hover_extras[key] = self._to_list(df_clean[col])

            fig = go.Figure()

            for i, cat in enumerate(unique_cats):
                mask = [c == cat for c in catalysts]
                indices = [j for j, m in enumerate(mask) if m]

                if not indices:
                    continue

                x_cat = [x_data[j] for j in indices]
                y_cat = [y_data[j] for j in indices]
                s_cat = [sizes[j] for j in indices]
                id_cat = [ids[j] for j in indices]

                hover_texts: List[str] = []
                for k, idx in enumerate(indices):
                    text = (f"<b>{id_cat[k]}</b><br>Catalyst: {cat}<br>"
                            f"Yield: {x_cat[k]:.1f}%<br>E-Factor: {y_cat[k]:.1f}")
                    for key, vals in hover_extras.items():
                        text += f"<br>{key}: {vals[idx]:.2f}"
                    hover_texts.append(text)

                fig.add_trace(go.Scatter(
                    x=x_cat, y=y_cat, mode='markers',
                    name=cat[:22] + '...' if len(cat) > 22 else cat,
                    marker=dict(
                        size=s_cat,
                        color=self.CHART_PALETTE[i % len(self.CHART_PALETTE)],
                        opacity=0.75, line=dict(width=1, color='white'),
                    ),
                    text=hover_texts,
                    hovertemplate='%{text}<extra></extra>',
                ))

            other_cats = [c for c in set(catalysts) if c not in unique_cats]
            if other_cats:
                other_idx = [j for j, c in enumerate(catalysts) if c in other_cats]
                if other_idx:
                    fig.add_trace(go.Scatter(
                        x=[x_data[j] for j in other_idx],
                        y=[y_data[j] for j in other_idx],
                        mode='markers',
                        name=f'Others ({len(other_cats)})',
                        marker=dict(size=10, color=self.colors['neutral'], opacity=0.5),
                        hovertemplate='Yield: %{x:.1f}%<br>E-Factor: %{y:.1f}<extra></extra>',
                    ))

            x_min_data, x_max_data = min(x_data, default=0), max(x_data, default=100)
            y_min_data, y_max_data = min(y_data, default=0), max(y_data, default=100)

            ideal_x0 = max(60, x_min_data + (x_max_data - x_min_data) * 0.6)
            ideal_y1 = min(50, y_min_data + (y_max_data - y_min_data) * 0.3)

            fig.add_shape(
                type="rect",
                x0=ideal_x0, x1=x_max_data * 1.02,
                y0=y_min_data, y1=ideal_y1,
                fillcolor="rgba(46, 204, 113, 0.1)",
                line=dict(color="green", width=1, dash="dash"),
            )

            fig.add_annotation(
                x=(ideal_x0 + x_max_data) / 2.0,
                y=ideal_y1 + (y_max_data - y_min_data) * 0.08,
                text="<b>Ideal Zone</b><br>(High Yield, Low Waste)",
                showarrow=False,
                font=dict(size=11, color='green'),
                bgcolor='white',
                bordercolor='darkgreen',
                borderwidth=1,
                borderpad=6,
            )

            if len(x_data) > 3:
                x_arr, y_arr = np.array(x_data, dtype=float), np.array(y_data, dtype=float)
                finite = np.isfinite(x_arr) & np.isfinite(y_arr)
                if finite.sum() > 3:
                    try:
                        z = np.polyfit(x_arr[finite], y_arr[finite], 1)
                        x_line = [float(x_arr[finite].min()), float(x_arr[finite].max())]
                        fig.add_trace(go.Scatter(
                            x=x_line, y=[z[0] * x + z[1] for x in x_line],
                            mode='lines', name='Trend',
                            line=dict(color='gray', width=2, dash='dash'),
                            hoverinfo='skip',
                        ))
                    except (np.linalg.LinAlgError, ValueError):
                        pass

            fig.update_layout(
                title=dict(text='Yield vs Environmental Impact (E-Factor)', x=0.5),
                xaxis_title='Yield (%)',
                yaxis_title='E-Factor (lower is better)',
                height=580, template='plotly_white',
                legend=dict(
                    yanchor="top", y=0.99, xanchor="left", x=1.02,
                    font=dict(size=9, color='black'),
                    bgcolor='white',
                    bordercolor='gray',
                    borderwidth=1,
                ),
            )

            return fig

        except Exception as e:
            logger.error(f"Yield vs E-factor error: {e}")
            return self._empty_figure(str(e))

    # ============================================================
    # CHART 4: CATALYST PERFORMANCE
    # ============================================================

    def plot_catalyst_performance(self, min_reactions: int = 2, top_n: int = 10) -> go.Figure:
        """Compare catalyst performance with error bars"""
        logger.info("Creating catalyst performance comparison...")

        try:
            if 'catalyst' not in self.df.columns:
                return self._empty_figure("No catalyst data")

            grouped = self.df.groupby('catalyst').agg(
                {'yield_percent': ['mean', 'std', 'count']}
            ).reset_index()
            grouped.columns = ['catalyst', 'avg_yield', 'std_yield', 'count']

            if 'rme' in self.df.columns:
                rme_stats = self.df.groupby('catalyst')['rme'].mean().reset_index()
                rme_stats.columns = ['catalyst', 'avg_rme']
                grouped = grouped.merge(rme_stats, on='catalyst', how='left')

            grouped['std_yield'] = grouped['std_yield'].fillna(0)
            grouped = grouped[grouped['count'] >= min_reactions]
            grouped = grouped.nlargest(
                min(top_n, len(grouped)), 'avg_yield'
            ).reset_index(drop=True)

            if len(grouped) == 0:
                return self._empty_figure(f"No catalysts with ≥{min_reactions} reactions")

            cats = [str(c)[:22] + '...' if len(str(c)) > 22 else str(c)
                    for c in grouped['catalyst']]
            yields = self._to_list(grouped['avg_yield'])
            stds = self._to_list(grouped['std_yield'])
            counts = [int(c) for c in grouped['count']]

            fig = go.Figure()

            fig.add_trace(go.Bar(
                x=cats, y=yields, name='Avg Yield (%)',
                marker_color=self.colors['primary'],
                error_y=dict(type='data', array=stds, visible=True,
                             color=self.colors['accent']),
                hovertemplate='<b>%{x}</b><br>Yield: %{y:.1f}% ± %{error_y.array:.1f}<extra></extra>',
            ))

            if 'avg_rme' in grouped.columns:
                fig.add_trace(go.Bar(
                    x=cats, y=self._to_list(grouped['avg_rme']),
                    name='Avg RME (%)', marker_color=self.colors['secondary'],
                    hovertemplate='<b>%{x}</b><br>RME: %{y:.1f}%<extra></extra>',
                ))

            for cat, y, s, n in zip(cats, yields, stds, counts):
                fig.add_annotation(x=cat, y=y + s + 3, text=f"n={n}",
                                   showarrow=False, font=dict(size=9, color='gray'))

            fig.update_layout(
                title=dict(
                    text=f'Top {len(cats)} Catalysts by Yield (min {min_reactions} reactions)',
                    x=0.5),
                xaxis_title='Catalyst', yaxis_title='Performance (%)',
                barmode='group', xaxis_tickangle=-45,
                height=550, template='plotly_white',
                legend=dict(orientation="h", yanchor="bottom",
                            y=1.02, xanchor="right", x=1),
            )

            return fig

        except Exception as e:
            logger.error(f"Catalyst performance error: {e}")
            return self._empty_figure(str(e))

    # ============================================================
    # CHART 5: SUSTAINABILITY SCORE
    # ============================================================

    def plot_sustainability_score(self, top_n: int = 15) -> go.Figure:
        """Sustainability score horizontal bar chart"""
        logger.info("Creating sustainability score chart...")

        try:
            score_col = 'green_score' if 'green_score' in self.df.columns else 'yield_percent'

            df_valid = self.df.dropna(subset=[score_col]).reset_index(drop=True)
            if len(df_valid) == 0:
                return self._empty_figure("No score data")

            df_top = df_valid.nlargest(min(top_n, len(df_valid)), score_col)
            df_top = df_top.sort_values(score_col, ascending=True).reset_index(drop=True)

            ids = self._to_str_list(df_top['reaction_id_short'])
            scores = self._to_list(df_top[score_col])

            min_s, max_s = min(scores, default=0), max(scores, default=100)
            if min_s == max_s:
                max_s = min_s + 1

            fig = go.Figure()

            fig.add_trace(go.Bar(
                y=ids, x=scores, orientation='h',
                marker=dict(color=scores, colorscale='Greens',
                            cmin=min_s, cmax=max_s, showscale=True,
                            colorbar=dict(title='Score', thickness=15)),
                text=[f'{s:.1f}' for s in scores], textposition='outside',
                hovertemplate='<b>%{y}</b><br>Score: %{x:.1f}<extra></extra>',
            ))

            fig.update_layout(
                title=dict(text=f'Top {len(ids)} by Sustainability Score', x=0.5),
                xaxis=dict(title='Green Score (0-100)', range=[0, max_s * 1.18]),
                yaxis_title='Reaction ID',
                height=max(420, len(ids) * 32),
                margin=dict(l=150, r=80), template='plotly_white',
            )

            return fig

        except Exception as e:
            logger.error(f"Sustainability score error: {e}")
            return self._empty_figure(str(e))

    # ============================================================
    # CHART 6: CO2 EMISSIONS
    # ============================================================

    def plot_co2_emissions(self) -> go.Figure:
        """CO2 emissions box plot with statistics"""
        logger.info("Creating CO2 emissions plot...")

        try:
            if 'co2_kg' not in self.df.columns:
                return self._empty_figure("No CO2 data")

            co2_data = self._to_list(self.df['co2_kg'].dropna())
            if len(co2_data) == 0:
                return self._empty_figure("No valid CO2 values")

            mean_v = float(np.mean(co2_data))
            median_v = float(np.median(co2_data))
            std_v = float(np.std(co2_data))
            min_v, max_v = float(min(co2_data)), float(max(co2_data))
            total_v = float(sum(co2_data))

            fig = go.Figure()

            fig.add_trace(go.Box(
                y=co2_data, name='CO₂ Emissions',
                marker=dict(color=self.colors['secondary'], size=6),
                fillcolor='rgba(52, 152, 219, 0.5)',
                line=dict(color=self.colors['secondary'], width=2),
                boxpoints='all', jitter=0.4, pointpos=-1.5, boxmean='sd',
                hovertemplate='CO₂: %{y:.4f} kg<extra></extra>',
            ))

            fig.add_annotation(
                x=0.98, y=0.98, xref='paper', yref='paper',
                text=(f"<b>CO₂ Statistics</b><br>─────────────<br>"
                      f"N: {len(co2_data)}<br>Mean: {mean_v:.4f} kg<br>"
                      f"Median: {median_v:.4f} kg<br>Std Dev: {std_v:.4f} kg<br>"
                      f"Min: {min_v:.4f} kg<br>Max: {max_v:.4f} kg<br>"
                      f"─────────────<br><b>Total: {total_v:.2f} kg</b>"),
                showarrow=False,
                font=dict(size=10, family='monospace', color='black'),
                align='left',
                bgcolor='white',
                bordercolor='gray',
                borderwidth=1,
                borderpad=10,
            )

            fig.update_layout(
                title=dict(text='CO₂ Emissions Distribution', x=0.5),
                yaxis_title='CO₂ Emissions (kg)',
                height=480, template='plotly_white', showlegend=False,
            )

            return fig

        except Exception as e:
            logger.error(f"CO2 emissions error: {e}")
            return self._empty_figure(str(e))

    # ============================================================
    # CHART 7: CORRELATION HEATMAP
    # ============================================================

    def plot_all_metrics_heatmap(self) -> go.Figure:
        """Correlation heatmap of all green chemistry metrics"""
        logger.info("Creating correlation heatmap...")

        metrics = [
            'yield_percent', 'atom_economy', 'rme', 'e_factor',
            'carbon_efficiency', 'pmi', 'energy_kwh', 'co2_kg', 'green_score',
        ]

        available = [m for m in metrics if m in self.df.columns]
        if len(available) < 2:
            return self._empty_figure("Need at least 2 metrics for correlation heatmap")

        corr = self.df[available].corr()
        corr = corr.dropna(axis=0, how='all').dropna(axis=1, how='all')

        if corr.empty or corr.shape[0] < 2:
            return self._empty_figure("Not enough variable metrics for correlation")

        corr_filled = corr.fillna(0)
        labels = [m.replace('_', ' ').title() for m in corr_filled.columns]
        z_values = corr_filled.values
        n = len(labels)

        annotations: List[dict] = []
        for i in range(n):
            for j in range(n):
                orig_val = corr.iloc[i, j]
                if pd.isna(orig_val):
                    text, font_color = "—", "#999999"
                else:
                    text = f"{z_values[i][j]:.2f}"
                    font_color = "white" if abs(z_values[i][j]) > 0.6 else "black"

                annotations.append(dict(
                    x=labels[j], y=labels[i], text=text,
                    font=dict(size=11, color=font_color),
                    showarrow=False, xref="x", yref="y",
                ))

        fig = go.Figure(data=go.Heatmap(
            z=z_values, x=labels, y=labels,
            colorscale='RdBu_r', zmid=0, zmin=-1, zmax=1,
            colorbar=dict(title='Correlation', thickness=15, len=0.8),
            hovertemplate='<b>%{x}</b> vs <b>%{y}</b><br>Correlation: %{z:.3f}<extra></extra>',
        ))

        fig.update_layout(
            annotations=annotations,
            title=dict(text='Correlation Matrix of Green Chemistry Metrics', x=0.5),
            height=550, width=700, template='plotly_white',
            xaxis=dict(tickangle=-45, side='bottom', tickfont=dict(size=10)),
            yaxis=dict(autorange='reversed', tickfont=dict(size=10)),
            margin=dict(l=120, r=60, t=80, b=120),
        )

        return fig

    # ============================================================
    # UTILITY METHODS
    # ============================================================

    def create_summary_table(self) -> pd.DataFrame:
        """Create summary statistics table"""
        metrics = [
            'yield_percent', 'atom_economy', 'rme', 'e_factor',
            'pmi', 'carbon_efficiency', 'energy_kwh', 'co2_kg', 'green_score',
        ]
        available = [m for m in metrics if m in self.df.columns]

        if not available:
            return pd.DataFrame()

        summary = self.df[available].describe().T
        summary = summary[['mean', 'min', 'max', 'std', '50%']]
        summary.columns = ['Mean', 'Min', 'Max', 'Std Dev', 'Median']
        return summary.round(3)

    def create_dashboard_figures(self) -> Dict[str, go.Figure]:
        """Generate all 7 essential figures"""
        logger.info("=" * 60)
        logger.info("Generating dashboard figures...")
        logger.info("=" * 60)

        figures: Dict[str, go.Figure] = {}
        methods = [
            ('yield_distribution', self.plot_yield_distribution),
            ('metrics_comparison', self.plot_metrics_comparison),
            ('yield_vs_efactor', self.plot_yield_vs_efactor),
            ('catalyst_performance', self.plot_catalyst_performance),
            ('sustainability_score', self.plot_sustainability_score),
            ('co2_emissions', self.plot_co2_emissions),
            ('correlation_heatmap', self.plot_all_metrics_heatmap),
        ]

        for name, method in methods:
            try:
                figures[name] = method()
                logger.info(f"  ✓ Created: {name}")
            except Exception as e:
                logger.error(f"  ✗ Failed: {name} - {e}")
                figures[name] = self._empty_figure(f"Error: {e}")

        logger.info(f"✓ Generated {len(figures)} figures")
        return figures

    def show_all_figures(self, figures: Dict[str, go.Figure]) -> Dict[str, bool]:
        """Display all figures using stable webbrowser method"""
        return {name: self.show_figure(fig, name) for name, fig in figures.items()}

    def save_figure(self, fig: go.Figure, filename: str, format: str = 'html') -> bool:
        """Save figure to file"""
        try:
            if format == 'html':
                fig.write_html(f"{filename}.html", include_plotlyjs='inline')
            else:
                fig.write_image(f"{filename}.{format}")
            logger.info(f"Saved: {filename}.{format}")
            return True
        except Exception as e:
            logger.error(f"Save failed: {e}")
            return False


def test_visualizations() -> None:
    """Test all visualizations"""
    from data_parser import ORDDataParser
    from metrics_calculator import GreenMetricsCalculator

    print("=" * 70)
    print("VISUALIZATION TEST - OPTIMIZED VERSION (7 graphs)")
    print("=" * 70)

    logger.info("Loading data...")
    parser = ORDDataParser('data/ord_search_results.pb')
    df = parser.parse_dataset()

    if df.empty:
        logger.error("No data")
        return

    logger.info("Calculating metrics...")
    calc = GreenMetricsCalculator(df)
    df_metrics = calc.calculate_all_metrics()

    logger.info("Creating visualizer...")
    viz = GreenChemistryVisualizer(df_metrics)

    print("\nGenerating figures...")
    figures = viz.create_dashboard_figures()

    print(f"\n✓ Created {len(figures)} figures:")
    for name in figures:
        print(f"  - {name}")

    print("\nDisplaying figures (opening in browser)...")
    results = viz.show_all_figures(figures)

    print("\nResults:")
    success = sum(results.values())
    print(f"  {success}/{len(results)} displayed successfully")
    for name, ok in results.items():
        print(f"  {'✓' if ok else '✗'} {name}")

    print("\n" + "=" * 70)
    print("SUMMARY TABLE")
    print("=" * 70)
    print(viz.create_summary_table().to_string())

    print("\n✓ COMPLETE!")


if __name__ == "__main__":
    test_visualizations()