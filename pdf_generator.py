"""
PDF Report Generator for Green Chemistry Dashboard
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
from datetime import datetime
from typing import Any, List, Optional, Dict, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether, Flowable, ListFlowable, ListItem
)
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

logger = logging.getLogger(__name__)

try:
    from pypdf import PdfReader, PdfWriter
    PYPDF_AVAILABLE = True
except Exception:
    PYPDF_AVAILABLE = False

try:
    from docx import Document
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    DOCX_AVAILABLE = True
except Exception:
    DOCX_AVAILABLE = False


class VShift(Flowable):
    """
    Wrap a flowable and shift it vertically by dy points.
    Positive dy moves UP, negative dy moves DOWN.
    """
    def __init__(self, flowable: Flowable, dy: float = 0):
        super().__init__()
        self.flowable = flowable
        self.dy = dy

    def wrap(self, availWidth: float, availHeight: float):
        return self.flowable.wrap(availWidth, availHeight)

    def draw(self):
        self.canv.saveState()
        self.canv.translate(0, self.dy)
        self.flowable.drawOn(self.canv, 0, 0)
        self.canv.restoreState()


class PDFReportGenerator:
    """Generate professional PDF and DOCX reports with robust charts."""

    COLOR_PRIMARY = colors.HexColor("#2ecc71")
    COLOR_DARK = colors.HexColor("#2c3e50")
    COLOR_MUTED = colors.HexColor("#7f8c8d")
    COLOR_LIGHT_BG = colors.HexColor("#f5f7fa")
    COLOR_TABLE_BG = colors.HexColor("#ecf0f1")
    COLOR_ACCENT = colors.HexColor("#8e44ad")
    COLOR_WARN = colors.HexColor("#e67e22")
    COLOR_DANGER = colors.HexColor("#e74c3c")

    def __init__(self, df: pd.DataFrame, df_filtered: pd.DataFrame, logo_path: str = "image/icon.png"):
        self.df = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
        self.df_filtered = df_filtered.copy() if isinstance(df_filtered, pd.DataFrame) else pd.DataFrame()

        self.logo_path = logo_path
        self.styles = getSampleStyleSheet()
        self._create_custom_styles()
        self.temp_files: List[str] = []

        self.page_size = letter
        self.left_margin = 50
        self.right_margin = 50
        self.top_margin = 56
        self.bottom_margin = 38
        self.content_width = self.page_size[0] - self.left_margin - self.right_margin

        self.report_title = "Green Chemistry Dashboard"
        self.report_subtitle = "Sustainable Reaction Analysis Report"
        self.dataset_label = "Ni-Catalyzed Suzuki\u2013Miyaura Cross-Coupling"

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------
    def _create_custom_styles(self) -> None:
        for name in [
            "ReportTitle", "ReportSubtitle", "SectionH1", "SectionH2",
            "Body", "Small", "Footer", "Caption", "KPI",
        ]:
            if name in self.styles.byName:
                del self.styles.byName[name]

        self.styles.add(ParagraphStyle(
            name="ReportTitle", parent=self.styles["Heading1"],
            fontName="Helvetica-Bold", fontSize=22, leading=26,
            textColor=self.COLOR_PRIMARY, alignment=TA_LEFT,
            spaceAfter=0, leftIndent=0,
        ))
        self.styles.add(ParagraphStyle(
            name="ReportSubtitle", parent=self.styles["BodyText"],
            fontName="Helvetica", fontSize=11, leading=14,
            textColor=self.COLOR_MUTED, alignment=TA_CENTER, spaceAfter=16,
        ))
        self.styles.add(ParagraphStyle(
            name="SectionH1", parent=self.styles["Heading2"],
            fontName="Helvetica-Bold", fontSize=14, leading=18,
            textColor=self.COLOR_DARK, spaceBefore=6, spaceAfter=8,
        ))
        self.styles.add(ParagraphStyle(
            name="SectionH2", parent=self.styles["Heading3"],
            fontName="Helvetica-Bold", fontSize=11.5, leading=14,
            textColor=self.COLOR_DARK, spaceBefore=6, spaceAfter=6,
        ))
        self.styles.add(ParagraphStyle(
            name="Body", parent=self.styles["BodyText"],
            fontName="Helvetica", fontSize=10.5, leading=14,
            textColor=self.COLOR_DARK, spaceAfter=8,
        ))
        self.styles.add(ParagraphStyle(
            name="Small", parent=self.styles["BodyText"],
            fontName="Helvetica", fontSize=9.5, leading=12,
            textColor=self.COLOR_DARK, spaceAfter=6,
        ))
        self.styles.add(ParagraphStyle(
            name="Caption", parent=self.styles["BodyText"],
            fontName="Helvetica-Oblique", fontSize=9, leading=11,
            textColor=self.COLOR_MUTED, spaceBefore=4, spaceAfter=10,
        ))
        self.styles.add(ParagraphStyle(
            name="Footer", parent=self.styles["BodyText"],
            fontName="Helvetica", fontSize=8, leading=10,
            textColor=self.COLOR_MUTED, alignment=TA_CENTER, spaceBefore=10,
        ))
        self.styles.add(ParagraphStyle(
            name="KPI", parent=self.styles["BodyText"],
            fontName="Helvetica-Bold", fontSize=11, leading=14,
            textColor=self.COLOR_DARK, alignment=TA_LEFT, spaceAfter=2,
        ))

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _format_co2(value: str) -> str:
        return f"CO<sub>2</sub>: {value}"

    @staticmethod
    def _primary_token(x: Any) -> str:
        if x is None or pd.isna(x):
            return ""
        s = str(x).strip()
        return s.split(";")[0].strip() if s else ""

    @property
    def _no_data(self) -> bool:
        """Check if filtered DataFrame is missing or empty."""
        return not isinstance(self.df_filtered, pd.DataFrame) or self.df_filtered.empty

    def _safe_series(self, col: str) -> Optional[pd.Series]:
        if self._no_data or col not in self.df_filtered.columns:
            return None
        s = pd.to_numeric(self.df_filtered[col], errors="coerce").dropna()
        return s if len(s) else None

    def _safe_value(self, col: str, fn: Any, default: str = "N/A", fmt: str = "{:.2f}") -> str:
        s = self._safe_series(col)
        if s is None:
            return default
        try:
            return fmt.format(fn(s))
        except Exception:
            return default

    def _sp(self, h: float) -> Spacer:
        return Spacer(1, h * inch)

    def _logo_image(self, width: float = 0.55 * inch, height: float = 0.55 * inch) -> Optional[Image]:
        try:
            if self.logo_path and os.path.exists(self.logo_path):
                return Image(self.logo_path, width=width, height=height)
        except Exception:
            pass
        return None

    def _clean_catalyst_column(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        out = df.copy()
        if "catalyst" in out.columns:
            out["catalyst"] = out["catalyst"].apply(self._primary_token)
        return out

    def _fig_to_path(self, fig: Any) -> Optional[str]:
        """Save matplotlib figure to temp PNG, return file path or None."""
        if fig is None:
            return None
        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            fig.savefig(tmp.name, format="png", dpi=200, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            self.temp_files.append(tmp.name)
            return tmp.name
        except Exception:
            try:
                plt.close(fig)
            except Exception:
                pass
            return None

    def save_fig(self, fig: Any, width: Optional[float] = None, height: Optional[float] = None) -> Optional[Image]:
        """Save figure and return ReportLab Image flowable."""
        if width is None:
            width = self.content_width
        if height is None:
            height = width * 0.58
        path = self._fig_to_path(fig)
        return Image(path, width=width, height=height) if path else None

    def cleanup(self) -> None:
        for f in self.temp_files:
            try:
                if os.path.exists(f):
                    os.unlink(f)
            except OSError:
                pass
        self.temp_files.clear()

    # ------------------------------------------------------------------
    # Header / footer decoration
    # ------------------------------------------------------------------
    def add_page_decorations(self, canvas: Any, doc: Any) -> None:
        page_num = canvas.getPageNumber()
        canvas.saveState()

        canvas.setStrokeColor(colors.HexColor("#dfe6e9"))
        canvas.setLineWidth(1)
        y = self.page_size[1] - 36
        canvas.line(self.left_margin, y, self.page_size[0] - self.right_margin, y)

        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(self.COLOR_MUTED)
        canvas.drawString(self.left_margin, y + 10, self.report_title)
        canvas.drawRightString(self.page_size[0] - self.right_margin, y + 10, self.dataset_label)

        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(self.COLOR_MUTED)
        canvas.drawString(self.left_margin, 18, datetime.now().strftime("Generated %Y-%m-%d %H:%M"))
        canvas.drawRightString(self.page_size[0] - self.right_margin, 18, f"Page {page_num}")

        canvas.restoreState()

    # ------------------------------------------------------------------
    # Charts (Matplotlib)
    # ------------------------------------------------------------------
    def create_yield_histogram(self, bins: int = 20) -> plt.Figure:
        fig, ax = plt.subplots(figsize=(8.2, 4.6))
        yields = self._safe_series("yield_percent")
        if yields is None:
            ax.text(0.5, 0.5, "No yield data available for the selected filters.",
                    ha="center", va="center", fontsize=11)
            ax.axis("off")
            plt.tight_layout()
            return fig

        ax.hist(yields, bins=bins, color="#2ecc71", edgecolor="white", alpha=0.90)
        mean_v = float(yields.mean())
        median_v = float(yields.median())
        ax.axvline(mean_v, color="#e74c3c", linestyle="--", linewidth=2, label=f"Mean: {mean_v:.1f}%")
        ax.axvline(median_v, color="#3498db", linestyle=":", linewidth=2, label=f"Median: {median_v:.1f}%")
        ax.set_xlabel("Yield (%)", fontsize=11)
        ax.set_ylabel("Count", fontsize=11)
        ax.set_title("Distribution of Reaction Yields", fontsize=13, fontweight="bold")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(frameon=False, fontsize=9, loc="upper right")
        plt.tight_layout()
        return fig

    def create_catalyst_performance_chart(self, min_reactions: int = 2, top_n: int = 10) -> plt.Figure:
        fig, ax = plt.subplots(figsize=(8.5, 5.5))

        df = pd.DataFrame() if self._no_data else self.df_filtered.copy()

        if df.empty or "catalyst" not in df.columns or "yield_percent" not in df.columns:
            ax.text(0.5, 0.5, "No data available for these filters", ha="center", va="center")
            ax.axis("off")
            plt.tight_layout()
            return fig

        actual_min_reactions = 1 if len(df) < 10 else min_reactions

        df["yield_percent"] = pd.to_numeric(df["yield_percent"], errors="coerce")
        grouped = df.groupby("catalyst").agg(
            {"yield_percent": ["mean", "std", "count"]}
        ).reset_index()
        grouped.columns = ["catalyst", "avg_yield", "std_yield", "count"]
        grouped["std_yield"] = grouped["std_yield"].fillna(0)
        grouped = grouped[grouped["count"] >= actual_min_reactions]

        if len(grouped) == 0:
            ax.text(0.5, 0.5, f"No catalysts meet the minimum count ({actual_min_reactions})",
                    ha="center", va="center")
            ax.axis("off")
            plt.tight_layout()
            return fig

        grouped = grouped.nlargest(top_n, "avg_yield").sort_values("avg_yield", ascending=True)
        n_cats = len(grouped)
        y_pos = np.arange(n_cats)

        bar_height = 0.35
        ax.barh(
            y_pos - bar_height / 2, grouped["avg_yield"], height=bar_height,
            color="#2ecc71", label="Avg Yield (%)", xerr=grouped["std_yield"],
            error_kw=dict(ecolor="#e74c3c", capsize=3, capthick=1.5, elinewidth=1.5),
        )

        if "rme" in df.columns:
            df["rme"] = pd.to_numeric(df["rme"], errors="coerce")
            rme_stats = df.groupby("catalyst")["rme"].mean().reset_index()
            grouped = grouped.merge(rme_stats, on="catalyst", how="left")
            if "rme" in grouped.columns:
                ax.barh(
                    y_pos + bar_height / 2, grouped["rme"].fillna(0),
                    height=bar_height, color="#3498db", label="Avg RME (%)",
                )

        for i, (yld, std, cnt) in enumerate(
            zip(grouped["avg_yield"], grouped["std_yield"], grouped["count"])
        ):
            offset = std + 1 if not np.isnan(std) else 1
            ax.text(yld + offset, i, f"n={cnt}", va="center", fontsize=8, color="#7f8c8d")

        ax.set_yticks(y_pos)
        ax.set_yticklabels(
            [str(c)[:30] + "..." if len(str(c)) > 30 else str(c) for c in grouped["catalyst"]],
            fontsize=9,
        )
        ax.set_xlabel("Performance (%)", fontsize=11)

        title_suffix = (
            f"(min {actual_min_reactions} reactions)"
            if actual_min_reactions > 1
            else "(all observations)"
        )
        ax.set_title(f"Top {n_cats} Catalysts by Yield {title_suffix}", fontsize=13)

        ax.legend(loc="lower right")
        ax.grid(axis="x", alpha=0.3)

        max_val = (grouped["avg_yield"] + grouped["std_yield"]).max()
        if pd.isna(max_val) or max_val == 0:
            max_val = 100
        ax.set_xlim(0, float(max_val) * 1.15)

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        plt.tight_layout()
        return fig

    def create_scatter_plot(self) -> plt.Figure:
        fig, ax = plt.subplots(figsize=(8.2, 4.6))
        needed = {"yield_percent", "e_factor", "rme"}

        if self._no_data or not needed.issubset(set(self.df_filtered.columns)):
            ax.text(0.5, 0.5, "Not enough data to plot Yield vs E-Factor for selected filters.",
                    ha="center", va="center", fontsize=11)
            ax.axis("off")
            plt.tight_layout()
            return fig

        data = self.df_filtered[list(needed)].copy()
        for c in needed:
            data[c] = pd.to_numeric(data[c], errors="coerce")
        data = data.dropna()

        if len(data) == 0:
            ax.text(0.5, 0.5, "No valid rows for Yield vs E-Factor.",
                    ha="center", va="center", fontsize=11)
            ax.axis("off")
            plt.tight_layout()
            return fig

        rme = data["rme"]
        rme_range = max(float(rme.max() - rme.min()), 1e-6)
        rme_norm = (rme - rme.min()) / rme_range

        sc = ax.scatter(
            data["yield_percent"], data["e_factor"],
            c=rme_norm, cmap="RdYlGn", s=55,
            alpha=0.78, edgecolors="white", linewidths=0.5,
        )

        e_factor_min = float(data["e_factor"].min())
        e_factor_max = float(data["e_factor"].max())
        e_factor_range = max(e_factor_max - e_factor_min, 1e-6)

        preferred_top = e_factor_min + e_factor_range * 0.25
        ax.axhspan(
            e_factor_min - e_factor_range * 0.05, preferred_top,
            xmin=0.6, xmax=1.0, facecolor="#2ecc71", alpha=0.10,
            edgecolor="green", linewidth=1,
        )

        yield_mid = float(data["yield_percent"].median())
        text_y = preferred_top + e_factor_range * 0.08
        ax.text(yield_mid, text_y, "Preferred region",
                ha="center", fontsize=10, color="green", fontweight="bold")
        ax.annotate(
            '', xy=(yield_mid, preferred_top),
            xytext=(yield_mid, text_y - e_factor_range * 0.02),
            arrowprops=dict(arrowstyle='->', color='green', lw=1.5),
        )

        if len(data) >= 3:
            x = data["yield_percent"].values.astype(float)
            y = data["e_factor"].values.astype(float)
            finite = np.isfinite(x) & np.isfinite(y)
            x_c, y_c = x[finite], y[finite]
            if len(x_c) >= 3:
                try:
                    m, b = np.polyfit(x_c, y_c, 1)
                    x_line = np.linspace(float(x_c.min()), float(x_c.max()), 50)
                    ax.plot(x_line, m * x_line + b, linestyle="--", color="gray",
                            linewidth=1.8, alpha=0.8)
                except (np.linalg.LinAlgError, ValueError):
                    pass

        ax.set_xlabel("Yield (%)", fontsize=11)
        ax.set_ylabel("E-Factor (Waste/Product)", fontsize=11)
        ax.set_title("Yield vs Environmental Impact (E-Factor)", fontsize=13, fontweight="bold")
        ax.grid(alpha=0.25)

        cbar = plt.colorbar(sc, ax=ax)
        cbar.set_label("RME (Normalized)", fontsize=9)
        plt.tight_layout()
        return fig

    def create_metrics_comparison(self) -> plt.Figure:
        fig, axes = plt.subplots(1, 3, figsize=(10.0, 4.0))
        needed = {"yield_percent", "atom_economy", "rme", "e_factor"}

        if self._no_data or not needed.issubset(set(self.df_filtered.columns)):
            for ax in axes:
                ax.axis("off")
            axes[1].text(0.5, 0.5, "Not enough metric data for selected filters.",
                        ha="center", va="center", fontsize=11)
            plt.tight_layout()
            return fig

        label_col = None
        for candidate in ["reaction_id", "catalyst", "product"]:
            if candidate in self.df_filtered.columns:
                label_col = candidate
                break

        keep_cols = list(needed)
        if label_col and label_col not in keep_cols:
            keep_cols.append(label_col)

        top = self.df_filtered[keep_cols].copy()
        for c in needed:
            top[c] = pd.to_numeric(top[c], errors="coerce")
        top = top.dropna(subset=list(needed))

        if len(top) == 0:
            for ax in axes:
                ax.axis("off")
            axes[1].text(0.5, 0.5, "No valid metric rows.",
                        ha="center", va="center", fontsize=11)
            plt.tight_layout()
            return fig

        top = top.nlargest(min(5, len(top)), "yield_percent")
        n = len(top)

        if label_col and label_col in top.columns:
            if label_col == "reaction_id":
                labels = [
                    str(x)[:16] + "..." if pd.notna(x) and len(str(x)) > 16
                    else str(x) if pd.notna(x) else f"Rxn #{i+1}"
                    for i, x in enumerate(top[label_col])
                ]
            elif label_col == "catalyst":
                labels = [
                    str(x)[:24] + "..." if pd.notna(x) and len(str(x)) > 24
                    else str(x) if pd.notna(x) else f"Rxn #{i+1}"
                    for i, x in enumerate(top[label_col])
                ]
            else:
                labels = [
                    str(x)[:20] + "..." if pd.notna(x) and len(str(x)) > 20
                    else str(x) if pd.notna(x) else f"Rxn #{i+1}"
                    for i, x in enumerate(top[label_col])
                ]
        else:
            labels = [f"Rxn #{i + 1}" for i in range(n)]

        axes[0].barh(range(n), top["atom_economy"].values, color="#3498db")
        axes[0].set_title("Atom Economy (%)", fontsize=10, fontweight="bold")
        axes[0].set_xlim(0, 100)

        axes[1].barh(range(n), top["rme"].values, color="#2ecc71")
        axes[1].set_title("RME (%)", fontsize=10, fontweight="bold")

        axes[2].barh(range(n), top["e_factor"].values, color="#e74c3c")
        axes[2].set_title("E-Factor", fontsize=10, fontweight="bold")

        for ax in axes:
            ax.set_yticks(range(n))
            ax.set_yticklabels(labels, fontsize=8)
            ax.grid(axis="x", alpha=0.25)

        plt.suptitle("Green Chemistry Metrics \u2014 Top Performing Reactions",
                    fontsize=12, fontweight="bold")
        plt.tight_layout()
        return fig

    def create_ci_chart(self, figsize: Tuple[float, float] = (8.2, 5.5)) -> Optional[plt.Figure]:
        try:
            from advanced_analytics import StatisticalAnalyzer
            analyzer = StatisticalAnalyzer(self.df_filtered)
            ci_df = analyzer.confidence_intervals()
            if ci_df is None or ci_df.empty or len(ci_df) < 2:
                return None

            expected = {"Catalyst", "N", "Mean_Yield", "CI_Lower", "CI_Upper"}
            if not expected.issubset(set(ci_df.columns)):
                return None

            ci_df = ci_df.head(8)
            fig, ax = plt.subplots(figsize=figsize)

            for i, (_, row) in enumerate(ci_df.iterrows()):
                ax.plot([row["CI_Lower"], row["CI_Upper"]], [i, i],
                        color="#2980b9", linewidth=4, alpha=0.75)
                ax.plot(row["Mean_Yield"], i, "o", color="#2c3e50", markersize=9)
                ax.text(row["CI_Upper"] + 1, i, f"{row['Mean_Yield']:.1f}%",
                        va="center", fontsize=10, color="#2c3e50")

            ax.set_yticks(range(len(ci_df)))
            ax.set_yticklabels([str(c)[:28] for c in ci_df["Catalyst"]], fontsize=10)
            ax.set_xlabel("Yield (%)", fontsize=12)
            ax.set_title("95% Confidence Intervals by Catalyst", fontsize=14, fontweight="bold")
            ax.grid(axis="x", alpha=0.25)
            plt.tight_layout()
            return fig
        except Exception:
            return None

    def create_pairwise_heatmap(self) -> Optional[plt.Figure]:
        try:
            from advanced_analytics import StatisticalAnalyzer
            analyzer = StatisticalAnalyzer(self.df_filtered)
            comparison = analyzer.compare_catalysts()

            if not comparison or "pairwise" not in comparison:
                return None

            pairwise = comparison.get("pairwise")
            if not isinstance(pairwise, pd.DataFrame) or pairwise.empty:
                return None
            if "P_Value" not in pairwise.columns:
                return None

            catalysts = list(set(
                pairwise["Catalyst_A"].tolist() + pairwise["Catalyst_B"].tolist()
            ))[:8]
            if len(catalysts) < 3:
                return None

            n = len(catalysts)
            matrix = np.ones((n, n))

            for _, row in pairwise.iterrows():
                cat_a = row.get("Catalyst_A", "")
                cat_b = row.get("Catalyst_B", "")
                p_val = float(row.get("P_Value", 1.0))
                if cat_a in catalysts and cat_b in catalysts:
                    i = catalysts.index(cat_a)
                    j = catalysts.index(cat_b)
                    matrix[i, j] = p_val
                    matrix[j, i] = p_val

            fig, ax = plt.subplots(figsize=(8.0, 6.5))
            im = ax.imshow(matrix, cmap="RdYlGn_r", vmin=0, vmax=0.1)

            ax.set_xticks(range(n))
            ax.set_yticks(range(n))
            ax.set_xticklabels([str(c)[:15] for c in catalysts], rotation=45, ha="right", fontsize=9)
            ax.set_yticklabels([str(c)[:15] for c in catalysts], fontsize=9)

            for i in range(n):
                for j in range(n):
                    if i != j:
                        p_val = matrix[i, j]
                        text_color = "#1a1a2e" if p_val < 0.05 else "#2c3e50"
                        ax.text(j, i, f"{p_val:.3f}", ha="center", va="center",
                                fontsize=9, fontweight="bold", color=text_color)
                    else:
                        ax.text(j, i, "\u2014", ha="center", va="center",
                                fontsize=10, color="#7f8c8d")

            ax.set_title(
                "Pairwise Comparison P-Values\n(Green = Significant Difference, p < 0.05)",
                fontsize=12, fontweight="bold",
            )

            cbar = plt.colorbar(im, ax=ax, shrink=0.8)
            cbar.set_label("P-Value", fontsize=10)

            ax.text(
                0.5, -0.18,
                "Values < 0.05 indicate statistically significant differences between catalysts",
                transform=ax.transAxes, ha="center", fontsize=9, style="italic", color="#7f8c8d",
            )
            plt.tight_layout()
            return fig
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Content helpers
    # ------------------------------------------------------------------
    def _make_table(
        self, data: List[List[Any]],
        header_bg: Any = None, body_bg: Any = None,
        col_widths: Any = None, compact: bool = True,
    ) -> Table:
        """
        Build a styled Table.
        compact=True  → original _styled_table  (font 10, pad 6/8, grid 0.6)
        compact=False → original _readable_table (font 9, pad 8/10, grid 0.8, ALIGN LEFT)
        """
        if header_bg is None:
            header_bg = self.COLOR_PRIMARY
        if body_bg is None:
            body_bg = self.COLOR_TABLE_BG

        fs = 10 if compact else 9
        pad_tb = 6 if compact else 8
        pad_lr = 8 if compact else 10
        grid_w = 0.6 if compact else 0.8

        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), fs),
            ("GRID", (0, 0), (-1, -1), grid_w, colors.HexColor("#bdc3c7")),
            ("BACKGROUND", (0, 1), (-1, -1), body_bg),
            ("LEFTPADDING", (0, 0), (-1, -1), pad_lr),
            ("RIGHTPADDING", (0, 0), (-1, -1), pad_lr),
            ("TOPPADDING", (0, 0), (-1, -1), pad_tb),
            ("BOTTOMPADDING", (0, 0), (-1, -1), pad_tb),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        if not compact:
            style_cmds.append(("ALIGN", (0, 0), (-1, -1), "LEFT"))

        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle(style_cmds))
        return t

    def _bullet_list(self, items: List[str]) -> ListFlowable:
        li = [ListItem(Paragraph(it, self.styles["Body"]), leftIndent=14) for it in items]
        return ListFlowable(li, bulletType="bullet", leftIndent=14)

    def _stats_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "comparison": None, "ci_df": None, "best": None,
            "pairwise_top": None, "error": None,
        }
        try:
            from advanced_analytics import StatisticalAnalyzer
            analyzer = StatisticalAnalyzer(self.df_filtered)
            payload["comparison"] = analyzer.compare_catalysts()
            payload["ci_df"] = analyzer.confidence_intervals()
            payload["best"] = analyzer.best_catalyst()

            comp = payload["comparison"]
            if comp and isinstance(comp.get("pairwise"), pd.DataFrame):
                pw = comp["pairwise"].copy()
                if "P_Value" in pw.columns:
                    pw = pw.sort_values("P_Value", ascending=True)
                payload["pairwise_top"] = pw.head(10)
        except Exception as e:
            payload["error"] = str(e)
        return payload

    def _recommendations_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"recs": [], "rules": [], "error": None}
        try:
            from advanced_analytics import ExpertSystem
            expert = ExpertSystem(self.df_filtered)
            for pr in ["yield", "sustainability", "balanced"]:
                rec = expert.get_recommendation(pr)
                if rec:
                    payload["recs"].append(rec)
            payload["rules"] = expert.extract_rules()
        except Exception as e:
            payload["error"] = str(e)
        return payload

    def _best_reaction_row(self) -> Optional[pd.Series]:
        if self._no_data:
            return None
        df = self.df_filtered.copy()

        for col in ["green_score", "yield_percent"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                cand = df.dropna(subset=[col])
                if len(cand):
                    return cand.sort_values(col, ascending=False).iloc[0]
        return None

    def _conclusions_text(self) -> Tuple[List[str], List[str], List[str]]:
        if self._no_data:
            return (
                ["No filtered reactions were available to summarize."],
                ["No conclusions can be drawn from an empty selection."],
                ["Adjust filters and regenerate the report."],
            )

        df = self.df_filtered
        y = pd.to_numeric(df.get("yield_percent", pd.Series(dtype=float)), errors="coerce")
        e = pd.to_numeric(df.get("e_factor", pd.Series(dtype=float)), errors="coerce")
        rme = pd.to_numeric(df.get("rme", pd.Series(dtype=float)), errors="coerce")
        temp = pd.to_numeric(df.get("temperature_c", pd.Series(dtype=float)), errors="coerce")
        time_h = pd.to_numeric(df.get("reaction_time_h", pd.Series(dtype=float)), errors="coerce")

        n = len(df)
        n_y = int(y.notna().sum())
        n_e = int(e.notna().sum())

        best_row = self._best_reaction_row()
        best_line = "Best reaction could not be determined."
        if best_row is not None:
            rid = best_row.get("reaction_id", "Unknown")
            by = best_row.get("yield_percent", None)
            bs = best_row.get("green_score", None)
            bc = best_row.get("catalyst", "Unknown")
            sv = best_row.get("solvent", "Unknown")
            by_s = f"{float(by):.1f}%" if by is not None and pd.notna(by) else "N/A"
            bs_s = f"{float(bs):.1f}" if bs is not None and pd.notna(bs) else "N/A"
            best_line = (
                f"Top observed reaction: ID {rid} | Catalyst: {bc} | "
                f"Solvent: {sv} | Yield: {by_s} | Green score: {bs_s}"
            )

        findings = [
            f"Filtered dataset size: {n} reactions (yield available for {n_y}, E-factor available for {n_e}).",
            (f"Average yield: {float(y.mean()):.1f}% (range {float(y.min()):.1f}%\u2013{float(y.max()):.1f}%)"
             if n_y else "Yield summary unavailable in filtered data."),
            (f"Average E-factor: {float(e.mean()):.1f} (best {float(e.min()):.1f}). Lower is better."
             if n_e else "E-factor summary unavailable in filtered data."),
            (f"Average RME: {float(rme.mean()):.1f}%."
             if int(rme.notna().sum()) else "RME summary unavailable in filtered data."),
            (f"Typical temperature: {float(temp.median()):.0f}\u00b0C; typical time: {float(time_h.median()):.1f} h."
             if int(temp.notna().sum()) and int(time_h.notna().sum())
             else "Temperature/time summary unavailable in filtered data."),
            best_line,
        ]

        limitations = [
            "Metrics are estimated using simplified assumptions (e.g., solvent volume per mmol, catalyst loading, and representative molecular weights).",
            "E-factor and CO2 are dominated by solvent assumptions at small scale; compare primarily within this dataset/assumption set.",
            "Catalyst labels may contain multiple components; grouping uses the primary token which may hide ligand/base effects.",
        ]

        next_steps = [
            "Standardize reagent roles and component identities (canonical catalyst/ligand/base mapping) to improve grouping accuracy.",
            "Collect or infer actual reaction scale and solvent volume to compute E-factor/PMI more realistically.",
            "Consider adding substrate descriptors (aryl halide type, boronic acid class) to explain variance beyond catalyst choice.",
        ]

        return findings, limitations, next_steps

    @staticmethod
    def _fmt_opt(val: Any, fmt: str = "{:.1f}", suffix: str = "", default: str = "N/A") -> str:
        if val is None or pd.isna(val):
            return default
        try:
            return fmt.format(float(val)) + suffix
        except (TypeError, ValueError):
            return default

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------
    def generate_full_report(self) -> io.BytesIO:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=letter,
            rightMargin=self.right_margin, leftMargin=self.left_margin,
            topMargin=self.top_margin, bottomMargin=self.bottom_margin,
            title="Green Chemistry Dashboard Report",
        )
        story: List[Any] = []

        if self._no_data:
            story.append(Paragraph(self.report_title, self.styles["ReportTitle"]))
            story.append(Paragraph(self.report_subtitle, self.styles["ReportSubtitle"]))
            story.append(Paragraph(
                f"Generated: {datetime.now().strftime('%B %d, %Y at %H:%M')}",
                self.styles["Small"],
            ))
            story.append(self._sp(0.15))
            story.append(Paragraph(
                "No reactions match the selected filters. Please broaden the filters and try again.",
                self.styles["Body"],
            ))
            doc.build(story, onFirstPage=self.add_page_decorations,
                      onLaterPages=self.add_page_decorations)
            buffer.seek(0)
            return buffer

        try:
            # ---- Page 1 ----
            logo_img = self._logo_image()
            if logo_img:
                title_p = Paragraph(self.report_title, self.styles["ReportTitle"])
                header_table = Table(
                    [[logo_img, title_p]],
                    colWidths=[0.6 * inch, 4.8 * inch],
                    hAlign="CENTER",
                )
                header_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (0, 0), "RIGHT"),
                    ("ALIGN", (1, 0), (1, 0), "LEFT"),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 6),
                    ("LEFTPADDING", (1, 0), (1, 0), 6),
                    ("RIGHTPADDING", (1, 0), (1, 0), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]))
                story.append(header_table)
            else:
                story.append(Paragraph(self.report_title, self.styles["ReportTitle"]))

            story.append(Paragraph(self.report_subtitle, self.styles["ReportSubtitle"]))
            story.append(Paragraph(
                f"<b>Generated:</b> {datetime.now().strftime('%B %d, %Y at %H:%M')}<br/>"
                f"<b>Dataset:</b> {self.dataset_label}<br/>"
                f"<b>Total reactions:</b> {len(self.df)} &nbsp;&nbsp; | &nbsp;&nbsp; "
                f"<b>Filtered:</b> {len(self.df_filtered)}",
                self.styles["Body"],
            ))
            story.append(self._sp(0.1))

            story.append(Paragraph("Executive Summary", self.styles["SectionH1"]))
            story.append(Paragraph(
                "This report summarizes yield performance and sustainability-oriented proxy metrics "
                "(Atom Economy, RME, E-factor, PMI, energy, and CO2 estimates) for the selected subset of reactions.",
                self.styles["Body"],
            ))

            cat_count = 0
            if "catalyst" in self.df_filtered.columns:
                try:
                    cat_count = int(self._clean_catalyst_column(self.df_filtered)["catalyst"].nunique())
                except Exception:
                    pass

            summary_data = [
                ["Metric", "Value"],
                ["Average Yield", f"{self._safe_value('yield_percent', np.mean, fmt='{:.1f}')}%"],
                ["Yield Range",
                 f"{self._safe_value('yield_percent', np.min, fmt='{:.1f}')}% \u2013 "
                 f"{self._safe_value('yield_percent', np.max, fmt='{:.1f}')}%"],
                ["Average RME", f"{self._safe_value('rme', np.mean, fmt='{:.1f}')}%"],
                ["Average E-Factor", self._safe_value('e_factor', np.mean, fmt='{:.1f}')],
                ["Best E-Factor", self._safe_value('e_factor', np.min, fmt='{:.1f}')],
                ["Atom Economy", f"{self._safe_value('atom_economy', np.mean, fmt='{:.1f}')}%"],
                ["Total CO2 (kg)", self._safe_value('co2_kg', np.sum, fmt='{:.2f}')],
                ["Catalysts Tested", str(cat_count)],
            ]
            story.append(self._make_table(
                summary_data, header_bg=self.COLOR_PRIMARY, body_bg=self.COLOR_TABLE_BG,
                col_widths=[3.1 * inch, self.content_width - 3.1 * inch],
            ))
            story.append(Paragraph("Generated by Green Chemistry Dashboard", self.styles["Footer"]))

            # ---- Page 2 ----
            story.append(PageBreak())
            story.append(Paragraph("Yield Distribution Analysis", self.styles["SectionH1"]))
            story.append(Paragraph(
                "The histogram summarizes yield spread and central tendency. A narrow distribution indicates "
                "consistent outcomes; a wide distribution may suggest sensitivity to conditions or substrate effects.",
                self.styles["Body"],
            ))
            img = self.save_fig(self.create_yield_histogram(bins=20), height=self.content_width * 0.52)
            if img:
                story.append(img)
                story.append(Paragraph(
                    "Figure: Yield distribution for the filtered selection.", self.styles["Caption"]))

            # ---- Page 3 ----
            story.append(PageBreak())
            story.append(Paragraph("Catalyst Performance Analysis", self.styles["SectionH1"]))
            story.append(Paragraph(
                "Catalyst performance comparison showing average yield with standard deviation error bars "
                "and average RME (Reaction Mass Efficiency). Only catalysts with at least 2 reactions are included.",
                self.styles["Body"],
            ))
            img = self.save_fig(
                self.create_catalyst_performance_chart(min_reactions=2, top_n=10),
                height=self.content_width * 0.62,
            )
            if img:
                story.append(img)
                story.append(Paragraph(
                    f"Figure: Catalyst Performance Analysis \u2014 Top catalysts by yield with error bars. "
                    f"Based on {len(self.df_filtered)} filtered reactions.",
                    self.styles["Caption"],
                ))

            # ---- Page 4 ----
            story.append(PageBreak())
            story.append(Paragraph("Yield vs Environmental Impact", self.styles["SectionH1"]))
            story.append(Paragraph(
                "The scatter plot relates yield to E-factor. Points are colored by normalized RME.",
                self.styles["Body"],
            ))
            img = self.save_fig(self.create_scatter_plot(), height=self.content_width * 0.52)
            if img:
                story.append(img)
                story.append(Paragraph(
                    "Figure: Yield vs E-factor with RME overlay (normalized).", self.styles["Caption"]))

            # ---- Page 5 ----
            story.append(PageBreak())
            story.append(Paragraph("Green Chemistry Metrics", self.styles["SectionH1"]))
            story.append(Paragraph(
                "This section compares key metrics for top-performing reactions.",
                self.styles["Body"],
            ))
            img = self.save_fig(self.create_metrics_comparison(),
                                width=self.content_width, height=self.content_width * 0.44)
            if img:
                story.append(img)
                story.append(Paragraph(
                    "Figure: Atom Economy, RME, and E-factor for top reactions by yield.",
                    self.styles["Caption"],
                ))

            # ---- Page 6 ----
            story.append(PageBreak())
            story.append(Paragraph("Statistical Analysis", self.styles["SectionH1"]))
            story.append(Paragraph(
                "We evaluate whether catalyst choice is associated with statistically distinguishable yield distributions.",
                self.styles["Body"],
            ))

            stats_payload = self._stats_payload()
            if stats_payload.get("error"):
                story.append(Paragraph(
                    f"Statistical analysis unavailable: {stats_payload['error']}", self.styles["Body"]))
            else:
                comparison = stats_payload.get("comparison")
                best = stats_payload.get("best")

                if comparison:
                    stat_val = comparison.get("statistic", comparison.get("f_statistic", 0.0))
                    p_val = comparison.get("p_value", 1.0)
                    test_type = comparison.get("test_type", "Overall test")
                    verdict = ("Significant: catalyst differences detected."
                               if comparison.get("significant", False)
                               else "Not significant: no clear catalyst differences.")
                    story.append(self._make_table(
                        [["Test", "Statistic", "p-value", "Interpretation"],
                         [str(test_type), f"{float(stat_val):.3f}", f"{float(p_val):.4f}", verdict]],
                        header_bg=self.COLOR_ACCENT, body_bg=colors.HexColor("#f8f4fc"),
                        col_widths=[1.8 * inch, 1.1 * inch, 1.0 * inch,
                                    self.content_width - (1.8 + 1.1 + 1.0) * inch],
                    ))
                    story.append(self._sp(0.12))

                if best:
                    story.append(Paragraph("Best Catalyst (conservative CI criterion)", self.styles["SectionH2"]))
                    story.append(Paragraph(
                        f"<b>{best.get('catalyst', 'Unknown')}</b><br/>"
                        f"Mean yield: {float(best.get('mean_yield', 0)):.1f}% &nbsp;&nbsp; "
                        f"95% CI: [{float(best.get('ci_lower', 0)):.1f}%, {float(best.get('ci_upper', 0)):.1f}%] "
                        f"&nbsp;&nbsp; n = {int(best.get('n_reactions', 0))}",
                        self.styles["Body"],
                    ))
                    story.append(self._sp(0.1))

                ci_fig = self.create_ci_chart(figsize=(8.2, 5.8))
                ci_img = self.save_fig(ci_fig, width=self.content_width, height=self.content_width * 0.58)
                if ci_img:
                    story.append(ci_img)
                    story.append(Paragraph(
                        "Figure: Confidence intervals of mean yield by catalyst (top groups).",
                        self.styles["Caption"],
                    ))

            # ---- Page 7 ----
            story.append(PageBreak())
            story.append(Paragraph("Statistical Analysis (Continued)", self.styles["SectionH1"]))

            if not stats_payload.get("error"):
                ci_df = stats_payload.get("ci_df")
                pairwise_top = stats_payload.get("pairwise_top")

                if isinstance(ci_df, pd.DataFrame) and not ci_df.empty:
                    expected_cols = {"Catalyst", "N", "Mean_Yield", "CI_Lower", "CI_Upper"}
                    if expected_cols.issubset(set(ci_df.columns)):
                        story.append(Paragraph("Confidence Interval Summary", self.styles["SectionH2"]))
                        tbl = [["Catalyst", "n", "Mean Yield", "95% CI Lower", "95% CI Upper"]]
                        for _, r in ci_df.head(12).iterrows():
                            tbl.append([
                                str(r["Catalyst"])[:32], str(int(r["N"])),
                                f"{float(r['Mean_Yield']):.1f}%",
                                f"{float(r['CI_Lower']):.1f}%",
                                f"{float(r['CI_Upper']):.1f}%",
                            ])
                        story.append(self._make_table(
                            tbl, header_bg=self.COLOR_ACCENT, body_bg=colors.HexColor("#f8f4fc"),
                            col_widths=[2.4 * inch, 0.6 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch],
                        ))
                    story.append(self._sp(0.15))

                heatmap_fig = self.create_pairwise_heatmap()
                if heatmap_fig:
                    heatmap_img = self.save_fig(
                        heatmap_fig, width=self.content_width * 0.85,
                        height=self.content_width * 0.65,
                    )
                    if heatmap_img:
                        story.append(heatmap_img)
                        story.append(Paragraph(
                            "Figure: Pairwise comparison p-values heatmap.", self.styles["Caption"]))
                elif isinstance(pairwise_top, pd.DataFrame) and not pairwise_top.empty:
                    story.append(Paragraph("Top Pairwise Differences", self.styles["SectionH2"]))
                    cols = [c for c in ["Catalyst_A", "Catalyst_B", "Mean_A", "Mean_B", "P_Value", "Significant"]
                            if c in pairwise_top.columns]
                    tbl = [["Catalyst A", "Catalyst B", "Mean A", "Mean B", "p-value", "Significant"]]
                    for _, r in pairwise_top[cols].head(10).iterrows():
                        tbl.append([
                            str(r.get("Catalyst_A", ""))[:20], str(r.get("Catalyst_B", ""))[:20],
                            f"{float(r.get('Mean_A', 0)):.1f}%", f"{float(r.get('Mean_B', 0)):.1f}%",
                            f"{float(r.get('P_Value', 1)):.4f}", str(r.get("Significant", "")),
                        ])
                    story.append(self._make_table(
                        tbl, header_bg=colors.HexColor("#34495e"), body_bg=colors.HexColor("#f2f6f9"),
                        col_widths=[1.2 * inch, 1.2 * inch, 0.8 * inch, 0.8 * inch, 0.8 * inch, 1.0 * inch],
                    ))

            story.append(Paragraph("Green Chemistry Dashboard | Statistical Section", self.styles["Footer"]))

            # ---- Page 8 ----
            story.append(PageBreak())
            story.append(Paragraph("Expert Recommendations", self.styles["SectionH1"]))
            story.append(Paragraph(
                "Recommendations are selected from observed best-performing reactions under the chosen priority.",
                self.styles["Body"],
            ))

            rec_payload = self._recommendations_payload()
            if rec_payload.get("error"):
                story.append(Paragraph(
                    f"Recommendations unavailable: {rec_payload['error']}", self.styles["Body"]))
            else:
                recs = rec_payload.get("recs", [])
                if recs:
                    story.append(Paragraph("Recommended Conditions", self.styles["SectionH2"]))
                    rec_tbl = [["Priority", "Catalyst", "Solvent", "Temp", "Time", "Yield", "E-factor"]]
                    for rec in recs:
                        rec_tbl.append([
                            str(rec.get("metric", "")).split(":")[0][:12],
                            str(rec.get("catalyst", "Unknown"))[:25],
                            str(rec.get("solvent", "Unknown"))[:18],
                            self._fmt_opt(rec.get("temperature"), "{:.0f}", "\u00b0C"),
                            self._fmt_opt(rec.get("time_h"), "{:.1f}", "h"),
                            self._fmt_opt(rec.get("yield"), "{:.1f}", "%"),
                            self._fmt_opt(rec.get("e_factor"), "{:.1f}"),
                        ])
                    story.append(self._make_table(
                        rec_tbl, header_bg=self.COLOR_PRIMARY, body_bg=self.COLOR_TABLE_BG,
                        col_widths=[0.85 * inch, 1.6 * inch, 1.2 * inch, 0.65 * inch,
                                    0.55 * inch, 0.65 * inch, 0.6 * inch],
                        compact=False,
                    ))
                    story.append(self._sp(0.15))

                best_row = self._best_reaction_row()
                if best_row is not None:
                    story.append(Paragraph("Best Observed Reaction", self.styles["SectionH2"]))
                    story.append(self._make_table(
                        [["Field", "Value"],
                         ["Reaction ID", str(best_row.get("reaction_id", "Unknown"))],
                         ["Catalyst", str(best_row.get("catalyst", "Unknown"))],
                         ["Solvent", str(best_row.get("solvent", "Unknown"))],
                         ["Yield", self._fmt_opt(best_row.get("yield_percent"), "{:.1f}", "%")],
                         ["E-factor", self._fmt_opt(best_row.get("e_factor"), "{:.1f}")],
                         ["Green score", self._fmt_opt(best_row.get("green_score"), "{:.1f}")]],
                        header_bg=colors.HexColor("#34495e"), body_bg=colors.HexColor("#f2f6f9"),
                        col_widths=[1.8 * inch, self.content_width - 1.8 * inch],
                        compact=False,
                    ))

            # ---- Page 9 ----
            story.append(PageBreak())
            story.append(Paragraph("Expert Recommendations (Continued)", self.styles["SectionH1"]))

            if not rec_payload.get("error"):
                rules = rec_payload.get("rules", [])
                if rules:
                    story.append(Paragraph("Observed Rules from Data", self.styles["SectionH2"]))
                    story.append(Paragraph(
                        "The following rules have been extracted from the dataset based on observed patterns:",
                        self.styles["Body"],
                    ))
                    story.append(self._sp(0.08))
                    lines: List[str] = []
                    for r in rules[:12]:
                        lines.append(f"<b>{r.get('type', 'RULE')}:</b> {r.get('rule', '')}")
                        ev = r.get("evidence", "")
                        if ev:
                            lines.append(f"<i>Evidence: {ev}</i>")
                    story.append(self._bullet_list(lines))
                else:
                    story.append(Paragraph(
                        "No specific rules could be extracted from the current selection.",
                        self.styles["Body"],
                    ))

            story.append(Paragraph("Green Chemistry Dashboard | Recommendations", self.styles["Footer"]))

            # ---- Page 10 ----
            story.append(PageBreak())
            story.append(Paragraph("Conclusions", self.styles["SectionH1"]))
            findings, limitations, next_steps = self._conclusions_text()

            story.append(Paragraph("Key Findings", self.styles["SectionH2"]))
            story.append(self._bullet_list(findings))
            story.append(Paragraph("Limitations and Assumptions", self.styles["SectionH2"]))
            story.append(self._bullet_list(limitations))
            story.append(Paragraph("Recommended Next Steps", self.styles["SectionH2"]))
            story.append(self._bullet_list(next_steps))
            story.append(Paragraph("Green Chemistry Dashboard | Conclusions", self.styles["Footer"]))

            doc.build(story, onFirstPage=self.add_page_decorations,
                      onLaterPages=self.add_page_decorations)
            buffer.seek(0)
            return buffer

        finally:
            self.cleanup()

    def generate_statistical_report(self) -> io.BytesIO:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=letter,
            rightMargin=self.right_margin, leftMargin=self.left_margin,
            topMargin=52, bottomMargin=self.bottom_margin,
            title="Statistical Analysis Report",
        )
        story: List[Any] = []

        if self._no_data:
            story.append(Paragraph("Statistical Analysis Report", self.styles["ReportTitle"]))
            story.append(Paragraph(
                "No reactions match the selected filters.", self.styles["Body"]))
            doc.build(story, onFirstPage=self.add_page_decorations,
                      onLaterPages=self.add_page_decorations)
            buffer.seek(0)
            return buffer

        try:
            story.append(Paragraph("Statistical Analysis Report", self.styles["ReportTitle"]))
            story.append(Paragraph(
                f"Generated: {datetime.now().strftime('%B %d, %Y')} | "
                f"Reactions analyzed: {len(self.df_filtered)}",
                self.styles["ReportSubtitle"],
            ))

            payload = self._stats_payload()
            if payload.get("error"):
                story.append(Paragraph(
                    f"Statistical analysis unavailable: {payload['error']}", self.styles["Body"]))
            else:
                comparison = payload.get("comparison")
                ci_df = payload.get("ci_df")
                best = payload.get("best")
                pairwise_top = payload.get("pairwise_top")

                if comparison:
                    stat_val = comparison.get("statistic", comparison.get("f_statistic", 0.0))
                    p_val = comparison.get("p_value", 1.0)
                    test_type = comparison.get("test_type", "Overall test")
                    result = "Significant (p<0.05)" if comparison.get("significant") else "Not significant"
                    story.append(self._make_table(
                        [["Test", "Statistic", "p-value", "Result"],
                         [str(test_type), f"{float(stat_val):.3f}", f"{float(p_val):.4f}", result]],
                        header_bg=self.COLOR_ACCENT, body_bg=colors.HexColor("#f8f4fc"),
                        col_widths=[2.0 * inch, 1.2 * inch, 1.1 * inch,
                                    self.content_width - 4.3 * inch],
                    ))
                    story.append(self._sp(0.12))

                if best:
                    story.append(Paragraph("Best Catalyst (conservative CI)", self.styles["SectionH2"]))
                    story.append(Paragraph(
                        f"<b>{best.get('catalyst', 'Unknown')}</b> \u2014 "
                        f"Mean {float(best.get('mean_yield', 0)):.1f}% "
                        f"(95% CI {float(best.get('ci_lower', 0)):.1f}\u2013"
                        f"{float(best.get('ci_upper', 0)):.1f}, "
                        f"n={int(best.get('n_reactions', 0))})",
                        self.styles["Body"],
                    ))

                ci_img = self.save_fig(
                    self.create_ci_chart(figsize=(8.2, 5.5)),
                    width=self.content_width, height=self.content_width * 0.55,
                )
                if ci_img:
                    story.append(ci_img)
                    story.append(Paragraph(
                        "Figure: Confidence intervals of mean yield by catalyst.",
                        self.styles["Caption"],
                    ))

                if isinstance(ci_df, pd.DataFrame) and not ci_df.empty:
                    expected_cols = {"Catalyst", "N", "Mean_Yield", "CI_Lower", "CI_Upper"}
                    if expected_cols.issubset(set(ci_df.columns)):
                        ci_data = [["Catalyst", "n", "Mean", "95% CI"]]
                        for _, row in ci_df.head(10).iterrows():
                            ci_data.append([
                                str(row["Catalyst"])[:28], str(int(row["N"])),
                                f"{float(row['Mean_Yield']):.1f}%",
                                f"[{float(row['CI_Lower']):.1f}, {float(row['CI_Upper']):.1f}]",
                            ])
                        story.append(self._make_table(
                            ci_data, header_bg=self.COLOR_ACCENT,
                            body_bg=colors.HexColor("#f8f4fc"),
                            col_widths=[2.7 * inch, 0.6 * inch, 0.9 * inch,
                                        self.content_width - 4.2 * inch],
                        ))

                if isinstance(pairwise_top, pd.DataFrame) and not pairwise_top.empty:
                    story.append(self._sp(0.12))
                    story.append(Paragraph("Top Pairwise Differences", self.styles["SectionH2"]))
                    cols = [c for c in ["Catalyst_A", "Catalyst_B", "Mean_A", "Mean_B",
                                        "P_Value", "Significant"]
                            if c in pairwise_top.columns]
                    tbl = [["A", "B", "Mean A", "Mean B", "p", "Sig"]]
                    for _, r in pairwise_top[cols].head(8).iterrows():
                        tbl.append([
                            str(r.get("Catalyst_A", ""))[:18],
                            str(r.get("Catalyst_B", ""))[:18],
                            f"{float(r.get('Mean_A', 0)):.1f}",
                            f"{float(r.get('Mean_B', 0)):.1f}",
                            f"{float(r.get('P_Value', 1)):.4f}",
                            str(r.get("Significant", "")),
                        ])
                    story.append(self._make_table(
                        tbl, header_bg=colors.HexColor("#34495e"),
                        body_bg=colors.HexColor("#f2f6f9"),
                        col_widths=[1.35 * inch, 1.35 * inch, 0.75 * inch, 0.75 * inch,
                                    0.75 * inch, self.content_width - 4.95 * inch],
                    ))

            story.append(Paragraph(
                "Green Chemistry Dashboard | Statistical Appendix", self.styles["Footer"]))
            doc.build(story, onFirstPage=self.add_page_decorations,
                      onLaterPages=self.add_page_decorations)
            buffer.seek(0)
            return buffer

        finally:
            self.cleanup()

    def generate_combined_pdf(self) -> io.BytesIO:
        return self.generate_full_report()

    def generate_full_report_docx(self) -> io.BytesIO:
        if not DOCX_AVAILABLE:
            raise ImportError("python-docx not installed. Run: pip install python-docx")

        try:
            doc = Document()
            normal = doc.styles["Normal"]
            normal.font.name = "Calibri"
            normal.font.size = Pt(11)

            if self.logo_path and os.path.exists(self.logo_path):
                try:
                    logo_para = doc.add_paragraph()
                    logo_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    logo_run = logo_para.add_run()
                    logo_run.add_picture(self.logo_path, width=Inches(0.4))
                except Exception:
                    pass  # Skip logo if image format unsupported

            p = doc.add_paragraph(self.report_title)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if p.runs:
                p.runs[0].bold = True
                p.runs[0].font.size = Pt(20)

            p2 = doc.add_paragraph(self.report_subtitle)
            p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if p2.runs:
                p2.runs[0].font.size = Pt(11)

            doc.add_paragraph(
                f"Generated: {datetime.now().strftime('%B %d, %Y at %H:%M')}\n"
                f"Dataset: {self.dataset_label}\n"
                f"Total reactions: {len(self.df)} | Filtered: {len(self.df_filtered)}"
            )

            if self._no_data:
                doc.add_paragraph("No reactions match the selected filters.")
                out = io.BytesIO()
                doc.save(out)
                out.seek(0)
                return out

            # Executive Summary
            doc.add_heading("Executive Summary", level=1)
            doc.add_paragraph(
                "This report summarizes yield performance and sustainability-oriented proxy metrics "
                "for the filtered selection."
            )

            summary_rows = [
                ("Average Yield", f"{self._safe_value('yield_percent', np.mean, fmt='{:.1f}')}%"),
                ("Average RME", f"{self._safe_value('rme', np.mean, fmt='{:.1f}')}%"),
                ("Average E-Factor", self._safe_value('e_factor', np.mean, fmt='{:.1f}')),
                ("Best E-Factor", self._safe_value('e_factor', np.min, fmt='{:.1f}')),
                ("Atom Economy", f"{self._safe_value('atom_economy', np.mean, fmt='{:.1f}')}%"),
                ("Total CO2 (kg)", self._safe_value('co2_kg', np.sum, fmt='{:.2f}')),
            ]
            if "catalyst" in self.df_filtered.columns:
                try:
                    summary_rows.append((
                        "Catalysts Tested",
                        str(int(self._clean_catalyst_column(self.df_filtered)["catalyst"].nunique())),
                    ))
                except Exception:
                    pass

            t = doc.add_table(rows=1, cols=2)
            t.style = "Table Grid"
            t.rows[0].cells[0].text = "Metric"
            t.rows[0].cells[1].text = "Value"
            for m, v in summary_rows:
                row = t.add_row().cells
                row[0].text = str(m)
                row[1].text = str(v)

            # Charts
            chart_sections = [
                ("Yield Distribution Analysis", self.create_yield_histogram, {"bins": 20}),
                ("Catalyst Performance Analysis", self.create_catalyst_performance_chart,
                 {"min_reactions": 2, "top_n": 10}),
                ("Yield vs Environmental Impact", self.create_scatter_plot, {}),
                ("Green Chemistry Metrics", self.create_metrics_comparison, {}),
            ]

            for title, method, kwargs in chart_sections:
                doc.add_page_break()
                doc.add_heading(title, level=1)
                try:
                    path = self._fig_to_path(method(**kwargs))
                    if path:
                        doc.add_picture(path, width=Inches(6.3))
                except Exception as e:
                    doc.add_paragraph(f"Chart generation failed: {e}")

            # Statistical Analysis
            doc.add_page_break()
            doc.add_heading("Statistical Analysis", level=1)
            payload = self._stats_payload()

            if payload.get("error"):
                doc.add_paragraph(f"Statistical analysis unavailable: {payload['error']}")
            else:
                comparison = payload.get("comparison")
                best = payload.get("best")
                ci_df = payload.get("ci_df")
                pairwise_top = payload.get("pairwise_top")

                if comparison:
                    stat_val = comparison.get("statistic", comparison.get("f_statistic", 0.0))
                    p_val = comparison.get("p_value", 1.0)
                    test_type = comparison.get("test_type", "Overall test")
                    doc.add_paragraph(
                        f"{test_type}: statistic={float(stat_val):.3f}, "
                        f"p={float(p_val):.4f}, significant={comparison.get('significant', False)}"
                    )

                if best:
                    doc.add_paragraph(
                        f"Best catalyst: {best['catalyst']} "
                        f"(Mean {best['mean_yield']:.1f}%, 95% CI "
                        f"{best['ci_lower']:.1f}\u2013{best['ci_upper']:.1f}, "
                        f"n={best['n_reactions']})"
                    )

                try:
                    ci_path = self._fig_to_path(self.create_ci_chart(figsize=(8.2, 5.5)))
                    if ci_path:
                        doc.add_picture(ci_path, width=Inches(6.3))
                except Exception:
                    pass

                if isinstance(ci_df, pd.DataFrame) and not ci_df.empty:
                    expected = {"Catalyst", "N", "Mean_Yield", "CI_Lower", "CI_Upper"}
                    if expected.issubset(ci_df.columns):
                        doc.add_paragraph("Confidence Interval Summary:")
                        tt = doc.add_table(rows=1, cols=4)
                        tt.style = "Table Grid"
                        for i, h in enumerate(["Catalyst", "n", "Mean", "95% CI"]):
                            tt.rows[0].cells[i].text = h
                        for _, r in ci_df.head(10).iterrows():
                            rr = tt.add_row().cells
                            rr[0].text = str(r["Catalyst"])[:28]
                            rr[1].text = str(int(r["N"]))
                            rr[2].text = f"{float(r['Mean_Yield']):.1f}%"
                            rr[3].text = f"[{float(r['CI_Lower']):.1f}, {float(r['CI_Upper']):.1f}]"

                if isinstance(pairwise_top, pd.DataFrame) and not pairwise_top.empty:
                    doc.add_paragraph("Top pairwise differences:")
                    tt = doc.add_table(rows=1, cols=4)
                    tt.style = "Table Grid"
                    for i, h in enumerate(["A", "B", "p", "Sig"]):
                        tt.rows[0].cells[i].text = h
                    for _, r in pairwise_top.head(8).iterrows():
                        rr = tt.add_row().cells
                        rr[0].text = str(r.get("Catalyst_A", ""))[:20]
                        rr[1].text = str(r.get("Catalyst_B", ""))[:20]
                        rr[2].text = f"{float(r.get('P_Value', 1)):.4f}"
                        rr[3].text = str(r.get("Significant", ""))

            # Expert Recommendations
            doc.add_page_break()
            doc.add_heading("Expert Recommendations", level=1)
            rec_payload = self._recommendations_payload()

            if rec_payload.get("error"):
                doc.add_paragraph(f"Recommendations unavailable: {rec_payload['error']}")
            else:
                recs = rec_payload.get("recs", [])
                rules = rec_payload.get("rules", [])

                if recs:
                    doc.add_paragraph("Recommended conditions:")
                    tt = doc.add_table(rows=1, cols=7)
                    tt.style = "Table Grid"
                    for i, h in enumerate(["Priority", "Catalyst", "Solvent", "Temp", "Time", "Yield", "E-factor"]):
                        tt.rows[0].cells[i].text = h
                    for rec in recs:
                        rr = tt.add_row().cells
                        rr[0].text = str(rec.get("metric", "")).split(":")[0]
                        rr[1].text = str(rec.get("catalyst", "Unknown"))[:25]
                        rr[2].text = str(rec.get("solvent", "Unknown"))[:18]
                        rr[3].text = self._fmt_opt(rec.get("temperature"), "{:.0f}", "\u00b0C")
                        rr[4].text = self._fmt_opt(rec.get("time_h"), "{:.1f}", "h")
                        rr[5].text = self._fmt_opt(rec.get("yield"), "{:.1f}", "%")
                        rr[6].text = self._fmt_opt(rec.get("e_factor"), "{:.1f}")

                if rules:
                    doc.add_paragraph("Observed rules from data:")
                    for r in rules[:10]:
                        doc.add_paragraph(
                            f"{r.get('type', 'RULE')}: {r.get('rule', '')}",
                            style="List Bullet",
                        )

            # Conclusions
            doc.add_page_break()
            doc.add_heading("Conclusions", level=1)
            findings, limitations, next_steps = self._conclusions_text()

            for heading, items in [
                ("Key Findings", findings),
                ("Limitations and Assumptions", limitations),
                ("Recommended Next Steps", next_steps),
            ]:
                doc.add_heading(heading, level=2)
                for it in items:
                    doc.add_paragraph(it, style="List Bullet")

            out = io.BytesIO()
            doc.save(out)
            out.seek(0)
            return out

        finally:
            self.cleanup()