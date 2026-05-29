"""
Advanced Analytics Module
Statistical analysis, expert system and sensitivity analysis
"""

import logging
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


class StatisticalAnalyzer:
    """Statistical analysis for catalyst comparison"""

    def __init__(self, df: pd.DataFrame, min_sample_size: int = 2, alpha: float = 0.05):
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pd.DataFrame, got {type(df).__name__}")
        if len(df) == 0:
            raise ValueError("DataFrame is empty")
        for col in ('catalyst', 'yield_percent'):
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        self.df = df.copy()
        self.min_sample_size = max(1, int(min_sample_size))
        self.alpha = float(alpha) if 0.0 < alpha < 1.0 else 0.05

    def _check_normality(self, data: np.ndarray) -> Tuple[bool, float]:
        """Check normality using Shapiro-Wilk test."""
        if len(data) < 3:
            return True, 1.0
        try:
            _, p = stats.shapiro(data)
            return p > self.alpha, float(p)
        except Exception:
            return True, 1.0

    def _cohens_d(self, g1: np.ndarray, g2: np.ndarray) -> float:
        """Calculate Cohen's d effect size."""
        n1, n2 = len(g1), len(g2)
        if n1 < 2 or n2 < 2:
            combined_std = float(np.std(np.concatenate([g1, g2])))
            return abs(float(np.mean(g1)) - float(np.mean(g2))) / combined_std if combined_std else 0.0

        denom = n1 + n2 - 2
        if denom <= 0:
            return 0.0
        pooled = np.sqrt(((n1 - 1) * np.var(g1, ddof=1) + (n2 - 1) * np.var(g2, ddof=1)) / denom)
        if pooled == 0 or not np.isfinite(pooled):
            return 0.0
        return abs(float(np.mean(g1)) - float(np.mean(g2))) / pooled

    def _get_catalyst_groups(self) -> Dict[str, np.ndarray]:
        """Get yield data grouped by catalyst, filtered by min sample size."""
        groups: Dict[str, np.ndarray] = {}
        for cat in self.df['catalyst'].dropna().unique():
            data = self.df[self.df['catalyst'] == cat]['yield_percent'].dropna().values
            if len(data) >= self.min_sample_size:
                groups[cat] = data
        return groups

    def compare_catalysts(self) -> Optional[Dict[str, Any]]:
        """Compare catalysts using ANOVA/Kruskal-Wallis + pairwise tests."""
        logger.info("Performing catalyst comparison analysis...")

        groups = self._get_catalyst_groups()
        if len(groups) < 2:
            logger.warning(f"Need >=2 groups with >={self.min_sample_size} samples each")
            return None

        logger.info(f"Comparing {len(groups)} catalyst groups")

        # Check normality
        all_normal = True
        for cat, data in groups.items():
            is_normal, p_val = self._check_normality(data)
            if not is_normal:
                logger.warning(f"'{cat}' may not be normal (Shapiro p={p_val:.4f})")
                all_normal = False

        # Omnibus test
        try:
            if all_normal:
                f_stat, p_value = stats.f_oneway(*groups.values())
                test_type = "ANOVA (parametric)"
            else:
                f_stat, p_value = stats.kruskal(*groups.values())
                test_type = "Kruskal-Wallis (non-parametric)"
            f_stat, p_value = float(f_stat), float(p_value)
            logger.info(f"{test_type}: stat={f_stat:.4f}, p={p_value:.4f}")
        except Exception as e:
            logger.error(f"Statistical test failed: {e}")
            return None

        # Pairwise comparisons
        pairwise: List[Dict[str, Any]] = []
        for cat1, cat2 in combinations(groups.keys(), 2):
            try:
                d1, d2 = groups[cat1], groups[cat2]

                if all_normal:
                    _, p = stats.ttest_ind(d1, d2, equal_var=False)
                    tname = "Welch's t-test"
                else:
                    _, p = stats.mannwhitneyu(d1, d2, alternative='two-sided')
                    tname = "Mann-Whitney U"

                m1, m2, p = float(np.mean(d1)), float(np.mean(d2)), float(p)
                cd = self._cohens_d(d1, d2)

                if cd < 0.2:
                    effect = "Negligible"
                elif cd < 0.5:
                    effect = "Small"
                elif cd < 0.8:
                    effect = "Medium"
                else:
                    effect = "Large"

                pairwise.append({
                    'Catalyst_A': cat1, 'Catalyst_B': cat2,
                    'Mean_A': round(m1, 2), 'Mean_B': round(m2, 2),
                    'Mean_Difference': round(abs(m1 - m2), 2),
                    'P_Value': round(p, 4),
                    'Significant': 'Yes' if p < self.alpha else 'No',
                    'Cohens_d': round(cd, 3), 'Effect_Size': effect,
                    'Better_Catalyst': cat1 if m1 > m2 else cat2,
                    'Test': tname,
                })
            except Exception as e:
                logger.warning(f"Pairwise {cat1} vs {cat2} failed: {e}")

        pw_df = pd.DataFrame(pairwise)
        if not pw_df.empty:
            pw_df = pw_df.sort_values('P_Value')

        return {
            'test_type': test_type, 'f_statistic': round(f_stat, 4),
            'p_value': round(p_value, 4), 'significant': p_value < self.alpha,
            'n_groups': len(groups),
            'groups': {k: len(v) for k, v in groups.items()},
            'pairwise': pw_df,
        }

    def confidence_intervals(self, confidence: float = 0.95) -> pd.DataFrame:
        """Calculate confidence intervals for each catalyst's yield."""
        if not (0.0 < confidence < 1.0):
            logger.warning(f"Confidence {confidence} out of range, using 0.95")
            confidence = 0.95

        logger.info(f"Calculating {confidence * 100:.0f}% confidence intervals...")
        results: List[Dict[str, Any]] = []

        for cat in self.df['catalyst'].dropna().unique():
            yields = self.df[self.df['catalyst'] == cat]['yield_percent'].dropna()
            n = len(yields)
            if n < self.min_sample_size:
                continue

            mu = float(yields.mean())
            sd = float(yields.std(ddof=1))
            se = sd / np.sqrt(n) if n > 0 else 0.0

            if n > 1 and se > 0 and np.isfinite(se):
                ci = stats.t.interval(confidence, n - 1, loc=mu, scale=se)
                lo, hi = float(ci[0]), float(ci[1])
            else:
                lo = hi = mu

            results.append({
                'Catalyst': cat, 'N': n,
                'Mean_Yield': round(mu, 2), 'Std_Dev': round(sd, 2),
                'Std_Error': round(se, 2),
                'CI_Lower': round(lo, 2), 'CI_Upper': round(hi, 2),
                'CI_Width': round(hi - lo, 2),
            })

        if not results:
            logger.warning("No catalysts with sufficient data for CI")
            return pd.DataFrame()

        result_df = pd.DataFrame(results).sort_values('Mean_Yield', ascending=False)
        logger.info(f"Calculated CIs for {len(result_df)} catalysts")
        return result_df

    def best_catalyst(self) -> Optional[Dict[str, Any]]:
        """Recommend best catalyst (highest lower CI bound — conservative)."""
        logger.info("Determining best catalyst...")

        ci_df = self.confidence_intervals()
        if ci_df.empty:
            logger.warning("Cannot determine best catalyst - insufficient data")
            return None

        ci_df = ci_df[ci_df['N'] >= self.min_sample_size]
        if ci_df.empty:
            logger.warning(f"No catalysts with >={self.min_sample_size} reactions")
            return None

        best = ci_df.loc[ci_df['CI_Lower'].idxmax()]
        result = {
            'catalyst': best['Catalyst'],
            'mean_yield': float(best['Mean_Yield']),
            'ci_lower': float(best['CI_Lower']),
            'ci_upper': float(best['CI_Upper']),
            'n_reactions': int(best['N']),
            'std_dev': float(best['Std_Dev']),
        }

        logger.info(
            f"Best: {result['catalyst']} (mean: {result['mean_yield']:.1f}%, "
            f"CI: [{result['ci_lower']:.1f}, {result['ci_upper']:.1f}])"
        )
        return result


class ExpertSystem:
    """Rule-based recommendation system"""

    def __init__(self, df: pd.DataFrame):
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pd.DataFrame, got {type(df).__name__}")
        for col in ('catalyst', 'yield_percent'):
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        self.df = df.copy()

    def get_recommendation(self, priority: str = 'balanced') -> Optional[Dict[str, Any]]:
        """Get recommendation based on priority: 'yield', 'sustainability', or 'balanced'."""
        if len(self.df) == 0:
            logger.warning("Cannot provide recommendation - no data")
            return None

        priority = str(priority).lower().strip()
        logger.info(f"Generating recommendation with priority: {priority}")

        try:
            if priority == 'yield':
                if 'yield_percent' not in self.df.columns:
                    return None
                valid = self.df['yield_percent'].dropna()
                if len(valid) == 0:
                    return None
                best_idx = valid.idxmax()
                metric = 'Highest Yield'

            elif priority == 'sustainability':
                if 'e_factor' not in self.df.columns:
                    return None
                valid = self.df['e_factor'].dropna()
                if len(valid) == 0:
                    return None
                best_idx = valid.idxmin()
                metric = 'Lowest E-Factor (Waste)'

            else:  # balanced
                if 'yield_percent' not in self.df.columns or 'e_factor' not in self.df.columns:
                    return None
                composite = (
                    self.df['yield_percent'].fillna(0) * 0.5
                    + (100.0 / (1.0 + self.df['e_factor'].fillna(100))) * 0.5
                )
                valid = composite.dropna()
                if len(valid) == 0:
                    return None
                best_idx = valid.idxmax()
                metric = 'Best Overall Balance'

            best = self.df.loc[best_idx]
            recommendation = {
                'metric': metric,
                'catalyst': best.get('catalyst', 'Unknown'),
                'solvent': best.get('solvent', 'Unknown'),
                'temperature': best.get('temperature_c'),
                'time_h': best.get('reaction_time_h'),
                'yield': best.get('yield_percent'),
                'e_factor': best.get('e_factor'),
                'rme': best.get('rme'),
                'green_score': best.get('green_score'),
                'reaction_id': best.get('reaction_id', 'Unknown'),
            }

            ry = recommendation['yield']
            if ry is not None and not pd.isna(ry):
                logger.info(f"Recommended: {recommendation['catalyst']} (yield: {float(ry):.1f}%)")
            else:
                logger.info(f"Recommended: {recommendation['catalyst']}")

            return recommendation

        except Exception as e:
            logger.error(f"Recommendation error: {e}")
            return None

    def extract_rules(self, top_quantile: float = 0.75, bottom_quantile: float = 0.25) -> List[Dict[str, Any]]:
        """Extract knowledge rules from data patterns."""
        logger.info("Extracting knowledge rules from data...")
        rules: List[Dict[str, Any]] = []

        if 'yield_percent' not in self.df.columns or 'e_factor' not in self.df.columns:
            logger.warning("Cannot extract rules - missing yield_percent or e_factor")
            return rules

        # Rule 1: Best performers (high yield AND low e-factor)
        try:
            yield_hi = self.df['yield_percent'].quantile(top_quantile)
            efactor_lo = self.df['e_factor'].quantile(bottom_quantile)

            top_rxns = self.df[
                (self.df['yield_percent'] > yield_hi) & (self.df['e_factor'] < efactor_lo)
            ]

            if len(top_rxns) > 0:
                for cat, count in top_rxns['catalyst'].value_counts().head(3).items():
                    sub = top_rxns[top_rxns['catalyst'] == cat]
                    rules.append({
                        'type': 'BEST PRACTICE',
                        'rule': f'Use catalyst: {cat}',
                        'evidence': f'{count} high-performing reactions',
                        'avg_yield': round(float(sub['yield_percent'].mean()), 1),
                        'avg_efactor': round(float(sub['e_factor'].mean()), 1),
                        'confidence': 'High' if count >= 3 else 'Medium',
                    })
        except Exception as e:
            logger.warning(f"Best practice rules failed: {e}")

        # Rule 2: Worst performers (low yield OR high e-factor)
        try:
            yield_lo = self.df['yield_percent'].quantile(bottom_quantile)
            efactor_hi = self.df['e_factor'].quantile(top_quantile)

            bot_rxns = self.df[
                (self.df['yield_percent'] < yield_lo) | (self.df['e_factor'] > efactor_hi)
            ]

            if len(bot_rxns) > 0:
                for cat, count in bot_rxns['catalyst'].value_counts().head(2).items():
                    total = len(self.df[self.df['catalyst'] == cat])
                    if total > 0 and (count / total) > 0.5:
                        sub = bot_rxns[bot_rxns['catalyst'] == cat]
                        rules.append({
                            'type': 'AVOID',
                            'rule': f'Avoid or optimize catalyst: {cat}',
                            'evidence': f'{count}/{total} poor-performing reactions',
                            'avg_yield': round(float(sub['yield_percent'].mean()), 1),
                            'avg_efactor': round(float(sub['e_factor'].mean()), 1),
                            'confidence': 'High' if count >= 3 else 'Medium',
                        })
        except Exception as e:
            logger.warning(f"Avoidance rules failed: {e}")

        # Rule 3: Catalyst profiles with color indicators
        try:
            for cat in self.df['catalyst'].dropna().unique():
                cat_data = self.df[self.df['catalyst'] == cat]
                if len(cat_data) < 2:
                    continue

                avg_yield = float(cat_data['yield_percent'].mean())
                avg_efactor = float(cat_data['e_factor'].mean())
                std_yield = float(cat_data['yield_percent'].std())
                n = len(cat_data)

                # Performance categorization with color indicators
                if avg_yield > 40 and avg_efactor < 50:
                    performance = '🟢 Excellent'
                    reliability = 'High' if std_yield < 15 else 'Variable'
                elif avg_yield > 25 and avg_efactor < 100:
                    performance = '🟡 Good'
                    reliability = 'Medium' if std_yield < 20 else 'Variable'
                elif avg_yield > 15 and avg_efactor < 200:
                    performance = '🟠 Moderate'
                    reliability = 'Medium' if std_yield < 25 else 'Variable'
                else:
                    performance = '🔴 Poor'
                    reliability = 'Low'

                if n >= 5:
                    conf = 'High'
                elif n >= 3:
                    conf = 'Medium'
                else:
                    conf = 'Low'

                rules.append({
                    'type': 'PROFILE',
                    'rule': f'{cat}: {performance}',
                    'evidence': f'{n} reactions',
                    'avg_yield': round(avg_yield, 1),
                    'avg_efactor': round(avg_efactor, 1),
                    'std_yield': round(std_yield, 1),
                    'reliability': reliability,
                    'confidence': conf,
                })
        except Exception as e:
            logger.warning(f"Catalyst profiles failed: {e}")

        logger.info(f"Extracted {len(rules)} rules")
        return rules


class SensitivityAnalyzer:
    """Analyze which factors most affect outcomes"""

    PREFERRED_COLS = [
        'temperature_c', 'reaction_time_h', 'yield_percent',
        'e_factor', 'rme', 'atom_economy', 'co2_kg', 'energy_kwh',
        'carbon_efficiency', 'pmi', 'green_score',
    ]

    def __init__(self, df: pd.DataFrame):
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pd.DataFrame, got {type(df).__name__}")
        if len(df) == 0:
            raise ValueError("DataFrame is empty")
        self.df = df.copy()
        self._numeric_cols = self.df.select_dtypes(include=[np.number]).columns.tolist()

    def correlation_analysis(self) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
        """Calculate correlations with yield and E-Factor."""
        logger.info("Performing correlation analysis...")
        empty = pd.Series(dtype=float)

        # Build column list: preferred first, then remaining numeric
        cols = [c for c in self.PREFERRED_COLS if c in self._numeric_cols]
        cols += [c for c in self._numeric_cols if c not in cols]

        if len(cols) < 2:
            logger.warning("Insufficient numeric columns for correlation")
            return pd.DataFrame(), empty, empty

        corr_data = self.df[cols].dropna(how='all', axis=1)
        if corr_data.shape[1] < 2 or corr_data.shape[0] < 2:
            logger.warning("Insufficient data for correlation after cleaning")
            return pd.DataFrame(), empty, empty

        corr_matrix = corr_data.corr()

        # Yield correlations
        if 'yield_percent' in corr_matrix.columns:
            yield_corr = corr_matrix['yield_percent'].sort_values(ascending=False)
            logger.info(f"Top yield correlations: {yield_corr.head(3).to_dict()}")
        else:
            yield_corr = empty
            logger.warning("'yield_percent' not in correlation matrix")

        # E-factor correlations
        if 'e_factor' in corr_matrix.columns:
            efactor_corr = corr_matrix['e_factor'].sort_values()
            logger.info(f"Top E-factor correlations: {efactor_corr.head(3).to_dict()}")
        else:
            efactor_corr = empty
            logger.warning("'e_factor' not in correlation matrix")

        return corr_matrix, yield_corr, efactor_corr

    def catalyst_importance(self) -> Dict[str, Any]:
        """Calculate how much catalyst choice matters (eta-squared)."""
        logger.info("Calculating catalyst importance...")

        err = {'variance_explained': 0.0, 'interpretation': '', 'error': True}

        if 'catalyst' not in self.df.columns or 'yield_percent' not in self.df.columns:
            logger.error("Required columns not found")
            err['interpretation'] = 'Cannot calculate - missing data'
            return err

        valid = self.df[['catalyst', 'yield_percent']].dropna()
        if len(valid) < 2:
            logger.warning("Insufficient data for catalyst importance")
            err['interpretation'] = 'Insufficient data'
            return err

        try:
            yields = valid['yield_percent'].values.astype(float)
            gm = float(np.mean(yields))
            ss_total = float(np.sum((yields - gm) ** 2))

            if ss_total == 0 or not np.isfinite(ss_total) or np.isnan(ss_total):
                logger.warning("No variance in yield data")
                err['interpretation'] = 'No variance in yield data'
                return err

            # SS_between = sum over groups: n_g * (mean_g - global_mean)^2
            ss_between = 0.0
            for cat in valid['catalyst'].unique():
                cat_yields = valid[valid['catalyst'] == cat]['yield_percent'].values.astype(float)
                ss_between += len(cat_yields) * (float(np.mean(cat_yields)) - gm) ** 2

            eta_sq = ss_between / ss_total
            vpct = eta_sq * 100.0

            # Interpretation (Cohen's guidelines)
            if eta_sq > 0.14:
                interp = 'LARGE effect - Catalyst choice is critical!'
                impact = 'Critical'
            elif eta_sq > 0.06:
                interp = 'MEDIUM effect - Catalyst choice matters'
                impact = 'Important'
            elif eta_sq > 0.01:
                interp = 'SMALL effect - Catalyst choice has minor impact'
                impact = 'Minor'
            else:
                interp = 'NEGLIGIBLE effect - Other factors dominate'
                impact = 'Negligible'

            logger.info(f"Catalyst explains {vpct:.1f}% of yield variance ({impact})")

            return {
                'variance_explained': round(vpct, 2),
                'eta_squared': round(eta_sq, 4),
                'interpretation': interp,
                'impact_level': impact,
                'ss_total': round(ss_total, 2),
                'ss_between': round(ss_between, 2),
                'error': False,
            }

        except Exception as e:
            logger.error(f"Catalyst importance error: {e}")
            err['interpretation'] = f'Calculation error: {str(e)}'
            return err


# ── Test ─────────────────────────────────────────────────────

def test_advanced_analytics() -> None:
    """Test the advanced analytics modules"""
    from data_parser import ORDDataParser
    from metrics_calculator import GreenMetricsCalculator

    logger.info("=" * 80)
    logger.info("ADVANCED ANALYTICS TEST")
    logger.info("=" * 80)

    parser = ORDDataParser('data/ord_search_results.pb')
    df = parser.parse_dataset()
    if df.empty:
        logger.error("No data loaded")
        return

    df_metrics = GreenMetricsCalculator(df).calculate_all_metrics()

    # ── Statistical Analysis ──
    print("\n" + "=" * 80)
    print("STATISTICAL ANALYSIS")
    print("=" * 80)

    stat = StatisticalAnalyzer(df_metrics)

    comparison = stat.compare_catalysts()
    if comparison:
        print(f"\n{comparison['test_type']}:")
        print(f"  F/H-statistic: {comparison['f_statistic']}")
        print(f"  P-value: {comparison['p_value']}")
        print(f"  Significant difference: {'Yes' if comparison['significant'] else 'No'}")
        print("\nPairwise Comparisons (top 5):")
        if not comparison['pairwise'].empty:
            print(comparison['pairwise'].head().to_string(index=False))

    ci_df = stat.confidence_intervals()
    if not ci_df.empty:
        print("\nConfidence Intervals (top 5 by mean yield):")
        print(ci_df.head().to_string(index=False))

    best = stat.best_catalyst()
    if best:
        print("\nBest Catalyst (by conservative estimate):")
        print(f"  Catalyst: {best['catalyst']}")
        print(f"  Mean Yield: {best['mean_yield']:.1f}%")
        print(f"  95% CI: [{best['ci_lower']:.1f}%, {best['ci_upper']:.1f}%]")
        print(f"  N reactions: {best['n_reactions']}")

    # ── Expert System ──
    print("\n" + "=" * 80)
    print("EXPERT SYSTEM RECOMMENDATIONS")
    print("=" * 80)

    expert = ExpertSystem(df_metrics)

    for priority in ['yield', 'sustainability', 'balanced']:
        rec = expert.get_recommendation(priority=priority)
        if rec:
            print(f"\n{rec['metric']}:")
            print(f"  Catalyst: {rec['catalyst']}")
            print(f"  Solvent: {rec['solvent']}")
            for key, label in [('temperature', 'Temperature'), ('yield', 'Yield'), ('e_factor', 'E-Factor')]:
                val = rec.get(key)
                if val is not None and not pd.isna(val):
                    print(f"  {label}: {float(val):.1f}")
                else:
                    print(f"  {label}: N/A")

    print("\nKnowledge Rules Extracted:")
    rules = expert.extract_rules()
    for i, rule in enumerate(rules[:10], 1):
        print(f"\n{i}. [{rule['type']}] {rule['rule']}")
        print(f"   Evidence: {rule['evidence']}")
        print(f"   Avg Yield: {rule['avg_yield']:.1f}%, Avg E-Factor: {rule['avg_efactor']:.1f}")
        if 'confidence' in rule:
            print(f"   Confidence: {rule['confidence']}")

    # ── Sensitivity Analysis ──
    print("\n" + "=" * 80)
    print("SENSITIVITY ANALYSIS")
    print("=" * 80)

    sens = SensitivityAnalyzer(df_metrics)

    corr_matrix, yield_corr, efactor_corr = sens.correlation_analysis()

    if not yield_corr.empty:
        print("\nTop Yield Correlations:")
        print(yield_corr.head(5).to_string())

    if not efactor_corr.empty:
        print("\nTop E-Factor Correlations (lower E-factor is better):")
        print(efactor_corr.head(5).to_string())

    importance = sens.catalyst_importance()
    if not importance.get('error'):
        print("\nCatalyst Importance:")
        print(f"  Variance Explained: {importance['variance_explained']:.1f}%")
        print(f"  Eta-squared: {importance['eta_squared']:.4f}")
        print(f"  Interpretation: {importance['interpretation']}")


if __name__ == "__main__":
    test_advanced_analytics()