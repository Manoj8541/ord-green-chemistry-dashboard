"""
Green Chemistry Metrics Calculator
Computes sustainability metrics for chemical reactions
"""

import math
import logging
from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class GreenMetricsCalculator:
    """Calculate green chemistry metrics for reactions"""

    def __init__(self, df: pd.DataFrame, reaction_scale_mmol: float = 1.0):
        """
        Initialize with parsed reaction DataFrame.

        Args:
            df: DataFrame with reaction data from data_parser
            reaction_scale_mmol: Reaction scale in mmol (default: 1.0)
        """
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pd.DataFrame, got {type(df).__name__}")

        self.df = df.copy()
        self.reaction_scale_mmol = reaction_scale_mmol

        # Validate required columns
        self._validate_dataframe()

        # Standard molecular weights (g/mol)
        self.mw_dict: Dict[str, float] = {
            'dioxane': 88.11,
            'thf': 72.11,
            'toluene': 92.14,
            'dmf': 73.09,
            'water': 18.02,
            'ethanol': 46.07,
            'methanol': 32.04,
            'acetone': 58.08,
            'ethyl acetate': 88.11,
            'K3PO4': 212.27,
            'K2CO3': 138.21,
            'Cs2CO3': 325.82,
            'aryl_halide': 150.0,
            'boronic_acid': 140.0,
            'product': 200.0,
            'KCl': 74.55,
            'boric_acid': 61.83,
        }

        # Solvent sustainability scores (1-10, higher is greener)
        self.solvent_scores: Dict[str, int] = {
            'water': 10,
            'ethanol': 8,
            'isopropanol': 7,
            'ethyl acetate': 7,
            'acetone': 6,
            'methanol': 6,
            'toluene': 5,
            'thf': 4,
            'dioxane': 3,
            'dmf': 2,
            'dcm': 1,
            'dichloromethane': 1,
            'chloroform': 1,
        }

        # Solvent densities (g/mL)
        self.solvent_densities: Dict[str, float] = {
            'dioxane': 1.03,
            'thf': 0.89,
            'toluene': 0.87,
            'dmf': 0.94,
            'water': 1.00,
            'ethanol': 0.79,
            'methanol': 0.79,
        }

        # Energy and emission factors
        self.energy_per_hour_heating: float = 0.5
        self.co2_per_kwh: float = 0.5
        self.ambient_temp: float = 25.0

        # Reaction assumptions
        self.catalyst_loading_mol_percent: float = 5.0
        self.catalyst_mw: float = 300.0
        self.base_equivalents: float = 2.0
        self.solvent_volume_ml: float = 2.0

        # Pre-calculate constant values used in every row
        self._mw_product: float = self.mw_dict.get('product', 200.0)
        self._mw_aryl_halide: float = self.mw_dict.get('aryl_halide', 150.0)
        self._mw_boronic_acid: float = self.mw_dict.get('boronic_acid', 140.0)
        self._total_reactant_mw: float = self._mw_aryl_halide + self._mw_boronic_acid
        self._mw_KCl: float = self.mw_dict.get('KCl', 74.55)
        self._mw_boric_acid: float = self.mw_dict.get('boric_acid', 61.83)
        self._mw_base: float = self.mw_dict.get('K3PO4', 212.27)

        # Pre-calculate atom economy (constant for Suzuki coupling)
        if self._total_reactant_mw > 0:
            self._atom_economy: float = min(
                (self._mw_product / self._total_reactant_mw) * 100.0, 100.0
            )
        else:
            self._atom_economy = 0.0

        # Pre-calculate constant mass terms (per mmol scale)
        self._reactant_mass_per_mmol: float = (
            (self._mw_aryl_halide + self._mw_boronic_acid) / 1000.0
        )
        self._catalyst_mass_per_mmol: float = (
            (self.catalyst_mw / 1000.0) * (self.catalyst_loading_mol_percent / 100.0)
        )
        self._base_mass_per_mmol: float = (
            (self._mw_base / 1000.0) * self.base_equivalents
        )
        self._byproduct_mw_sum: float = (self._mw_KCl + self._mw_boric_acid) / 1000.0
        self._product_mass_factor: float = self._mw_product / 1000.0

    def _validate_dataframe(self) -> None:
        """Validate that DataFrame has required columns"""
        required_columns = ['yield_percent']
        optional_columns = ['temperature_c', 'reaction_time_h', 'solvent', 'catalyst']

        missing_required = [col for col in required_columns if col not in self.df.columns]
        if missing_required:
            raise ValueError(f"DataFrame missing required columns: {missing_required}")

        missing_optional = [col for col in optional_columns if col not in self.df.columns]
        if missing_optional:
            logger.warning(f"DataFrame missing optional columns: {missing_optional}")

    @staticmethod
    def _validate_numeric(value: Optional[float]) -> Optional[float]:
        """
        Validate numeric value (check for NaN, infinity).

        Args:
            value: Numeric value to validate

        Returns:
            Validated value or None if invalid
        """
        if value is None:
            return None

        try:
            fval = float(value)
        except (TypeError, ValueError):
            return None

        if math.isnan(fval) or math.isinf(fval):
            return None

        return fval

    @staticmethod
    def _validate_yield(yield_pct: Optional[float]) -> Optional[float]:
        """
        Validate and cap yield percentage.

        Args:
            yield_pct: Yield percentage to validate

        Returns:
            Validated yield (0-100) or None
        """
        if yield_pct is None:
            return None

        try:
            if pd.isna(yield_pct):
                return None
            return min(max(float(yield_pct), 0.0), 100.0)
        except (TypeError, ValueError):
            return None

    def _clean_solvent_name(self, solvent: Optional[str]) -> str:
        """
        Clean solvent name by removing duplicates.

        Args:
            solvent: Raw solvent string

        Returns:
            Cleaned solvent string
        """
        if solvent is None or pd.isna(solvent) or not solvent:
            return ''

        parts = [s.strip() for s in str(solvent).split(';')]
        unique_parts: List[str] = []
        seen: set = set()

        for part in parts:
            lower = part.lower()
            if lower and lower not in seen:
                unique_parts.append(part)
                seen.add(lower)

        return '; '.join(unique_parts) if unique_parts else ''

    def calculate_atom_economy(self, row: pd.Series) -> Optional[float]:
        """
        Calculate Atom Economy (constant for Suzuki coupling).

        Args:
            row: DataFrame row

        Returns:
            Atom economy percentage (0-100)
        """
        return self._validate_numeric(self._atom_economy)

    def calculate_reaction_mass_efficiency(self, row: pd.Series) -> Optional[float]:
        """
        Calculate Reaction Mass Efficiency (RME).
        Uses pre-calculated atom_economy column if available.

        Args:
            row: DataFrame row

        Returns:
            RME percentage (0-100)
        """
        try:
            # Use pre-calculated value if available, avoid recalculation
            ae = row.get('atom_economy') if 'atom_economy' in row.index else None
            if ae is None or pd.isna(ae):
                ae = self._atom_economy

            yield_pct = self._validate_yield(row.get('yield_percent'))

            if ae is None or yield_pct is None:
                return None

            rme = (float(ae) * yield_pct) / 100.0
            return self._validate_numeric(rme)

        except (TypeError, ValueError):
            return None

    def calculate_e_factor(self, row: pd.Series) -> Optional[float]:
        """
        Calculate E-Factor (Environmental Factor).

        Args:
            row: DataFrame row

        Returns:
            E-factor (kg waste / kg product)
        """
        try:
            yield_pct = self._validate_yield(row.get('yield_percent'))

            if yield_pct is None or yield_pct <= 0:
                return None

            scale_mmol = self.reaction_scale_mmol
            yield_fraction = yield_pct / 100.0

            # Product mass (g)
            product_mass = self._product_mass_factor * scale_mmol * yield_fraction
            if product_mass <= 0:
                return None

            # Reactant masses (g)
            reactant_mass = self._reactant_mass_per_mmol * scale_mmol

            # Catalyst mass (g)
            catalyst_mass = self._catalyst_mass_per_mmol * scale_mmol

            # Base mass (g)
            base_mass = self._base_mass_per_mmol * scale_mmol

            # Solvent mass (g)
            solvent_raw = row.get('solvent', 'dioxane')
            solvent_name = self._clean_solvent_name(solvent_raw)
            solvent_key = solvent_name.split(';')[0].strip().lower() if solvent_name else 'dioxane'
            solvent_density = self.solvent_densities.get(solvent_key, 1.0)
            solvent_volume_ml = self.solvent_volume_ml * scale_mmol
            solvent_mass = solvent_volume_ml * solvent_density

            # Byproducts mass (g)
            byproduct_mass = self._byproduct_mw_sum * scale_mmol * yield_fraction

            # Unreacted starting materials (g)
            unreacted_sm = reactant_mass * (1.0 - yield_fraction)

            # Total waste
            waste_mass = (
                solvent_mass + catalyst_mass + base_mass +
                byproduct_mass + unreacted_sm
            )

            e_factor = waste_mass / product_mass
            return self._validate_numeric(e_factor)

        except (TypeError, ValueError, ZeroDivisionError):
            return None

    def calculate_process_mass_intensity(self, row: pd.Series) -> Optional[float]:
        """
        Calculate Process Mass Intensity (PMI).
        Uses pre-calculated e_factor column if available.

        Args:
            row: DataFrame row

        Returns:
            PMI (kg total / kg product)
        """
        try:
            # Use pre-calculated value if available, avoid recalculation
            e_factor = row.get('e_factor') if 'e_factor' in row.index else None

            if e_factor is None or pd.isna(e_factor):
                e_factor = self.calculate_e_factor(row)

            if e_factor is None:
                return None

            pmi = float(e_factor) + 1.0
            return self._validate_numeric(pmi)

        except (TypeError, ValueError):
            return None

    def calculate_carbon_efficiency(self, row: pd.Series) -> Optional[float]:
        """
        Calculate Carbon Efficiency.

        Args:
            row: DataFrame row

        Returns:
            Carbon efficiency percentage (0-100)
        """
        try:
            yield_pct = self._validate_yield(row.get('yield_percent'))
            if yield_pct is None:
                return None

            # In Suzuki coupling, carbon atoms are conserved
            carbon_eff = min(yield_pct, 100.0)
            return self._validate_numeric(carbon_eff)

        except (TypeError, ValueError, ZeroDivisionError):
            return None

    def calculate_solvent_score(self, row: pd.Series) -> float:
        """
        Calculate solvent sustainability score (1-10).

        Args:
            row: DataFrame row

        Returns:
            Solvent score (1-10, higher is greener)
        """
        try:
            solvent = row.get('solvent', '')

            if solvent is None or pd.isna(solvent) or solvent == '':
                return 5.0

            solvent_clean = self._clean_solvent_name(solvent)
            solvent_lower = solvent_clean.lower()

            for solvent_name, score in self.solvent_scores.items():
                if solvent_name in solvent_lower:
                    return float(score)

            return 5.0

        except (TypeError, ValueError):
            return 5.0

    def estimate_energy_consumption(self, row: pd.Series) -> Optional[float]:
        """
        Estimate energy consumption (kWh).

        Args:
            row: DataFrame row

        Returns:
            Energy consumption in kWh
        """
        try:
            temp = row.get('temperature_c')
            time_h = row.get('reaction_time_h')

            if temp is None or pd.isna(temp):
                temp = 60.0
            else:
                temp = float(temp)

            if time_h is None or pd.isna(time_h):
                time_h = 12.0
            else:
                time_h = float(time_h)

            if time_h < 0 or time_h > 1000:
                return None

            temp_diff = max(temp - self.ambient_temp, 0.0)

            baseline = 0.05
            heating_energy = (temp_diff / 100.0) * self.energy_per_hour_heating * time_h
            stirring_energy = 0.02 * time_h

            total_energy = baseline + heating_energy + stirring_energy
            return self._validate_numeric(round(total_energy, 4))

        except (TypeError, ValueError):
            return None

    def estimate_co2_footprint(self, row: pd.Series) -> Optional[float]:
        """
        Estimate CO2 emissions (kg CO2).
        Uses pre-calculated energy_kwh column if available.

        Args:
            row: DataFrame row

        Returns:
            CO2 emissions in kg
        """
        try:
            # Use pre-calculated value if available
            energy = row.get('energy_kwh') if 'energy_kwh' in row.index else None

            if energy is None or pd.isna(energy):
                energy = self.estimate_energy_consumption(row)

            if energy is None:
                return None

            co2 = float(energy) * self.co2_per_kwh
            return self._validate_numeric(round(co2, 4))

        except (TypeError, ValueError):
            return None

    def calculate_green_score(self, row: pd.Series) -> Optional[float]:
        """
        Calculate composite Green Chemistry Score (0-100).

        Args:
            row: DataFrame row

        Returns:
            Composite green score (0-100)
        """
        try:
            ae = row.get('atom_economy')
            rme = row.get('rme')
            e_factor = row.get('e_factor')
            carbon_eff = row.get('carbon_efficiency')
            solvent_score = row.get('solvent_score')
            yield_pct = self._validate_yield(row.get('yield_percent'))

            scores: List[float] = []
            weights: List[float] = []

            if ae is not None and not pd.isna(ae):
                scores.append(float(ae))
                weights.append(0.15)

            if rme is not None and not pd.isna(rme):
                scores.append(float(rme))
                weights.append(0.20)

            if e_factor is not None and not pd.isna(e_factor) and float(e_factor) > 0:
                e_score = max(0.0, 100.0 - (float(e_factor) * 2.0))
                scores.append(e_score)
                weights.append(0.20)

            if carbon_eff is not None and not pd.isna(carbon_eff):
                scores.append(float(carbon_eff))
                weights.append(0.15)

            if solvent_score is not None and not pd.isna(solvent_score):
                scores.append(float(solvent_score) * 10.0)
                weights.append(0.15)

            if yield_pct is not None:
                scores.append(float(yield_pct))
                weights.append(0.15)

            if not scores:
                return None

            total_weight = sum(weights)
            if total_weight <= 0:
                return None

            green_score = sum(s * w for s, w in zip(scores, weights)) / total_weight
            green_score = max(0.0, min(100.0, green_score))

            return round(green_score, 1)

        except (TypeError, ValueError):
            return None

    def calculate_all_metrics(self, show_progress: bool = True) -> pd.DataFrame:
        """
        Calculate all green chemistry metrics and add to DataFrame.

        Args:
            show_progress: Whether to show progress for large datasets

        Returns:
            DataFrame with added metric columns
        """
        if self.df.empty:
            logger.warning("DataFrame is empty — no metrics to calculate")
            return self.df

        logger.info("Calculating green chemistry metrics...")

        total = len(self.df)

        logger.info("  → Calculating atom economy...")
        self.df['atom_economy'] = self.df.apply(self.calculate_atom_economy, axis=1)

        logger.info("  → Calculating reaction mass efficiency...")
        self.df['rme'] = self.df.apply(self.calculate_reaction_mass_efficiency, axis=1)

        logger.info("  → Calculating E-factor...")
        self.df['e_factor'] = self.df.apply(self.calculate_e_factor, axis=1)

        logger.info("  → Calculating process mass intensity...")
        self.df['pmi'] = self.df.apply(self.calculate_process_mass_intensity, axis=1)

        logger.info("  → Calculating carbon efficiency...")
        self.df['carbon_efficiency'] = self.df.apply(self.calculate_carbon_efficiency, axis=1)

        logger.info("  → Calculating solvent scores...")
        self.df['solvent_score'] = self.df.apply(self.calculate_solvent_score, axis=1)

        logger.info("  → Estimating energy consumption...")
        self.df['energy_kwh'] = self.df.apply(self.estimate_energy_consumption, axis=1)

        logger.info("  → Estimating CO2 footprint...")
        self.df['co2_kg'] = self.df.apply(self.estimate_co2_footprint, axis=1)

        logger.info("  → Calculating composite green scores...")
        self.df['green_score'] = self.df.apply(self.calculate_green_score, axis=1)

        # Print summary
        logger.info("✓ Calculated metrics for all reactions")
        metric_cols = [
            'atom_economy', 'rme', 'e_factor', 'pmi',
            'carbon_efficiency', 'solvent_score', 'energy_kwh',
            'co2_kg', 'green_score',
        ]
        logger.info(f"✓ New columns: {', '.join(metric_cols)}")

        for col in metric_cols:
            non_null = self.df[col].notna().sum()
            percentage = (non_null / total) * 100 if total > 0 else 0.0
            logger.info(f"  {col}: {non_null}/{total} ({percentage:.1f}%)")

        return self.df

    def get_summary_statistics(self) -> pd.DataFrame:
        """
        Get summary statistics for all metrics.

        Returns:
            DataFrame with descriptive statistics
        """
        metric_columns = [
            'yield_percent', 'atom_economy', 'rme', 'e_factor', 'pmi',
            'carbon_efficiency', 'solvent_score', 'energy_kwh',
            'co2_kg', 'green_score',
        ]

        available_metrics = [col for col in metric_columns if col in self.df.columns]

        if not available_metrics:
            logger.warning("No metric columns found in DataFrame")
            return pd.DataFrame()

        return self.df[available_metrics].describe()

    def get_best_reactions(self, n: int = 10, metric: str = 'green_score') -> pd.DataFrame:
        """
        Get top N reactions by specified metric.

        Args:
            n: Number of reactions to return
            metric: Metric to sort by (default: green_score)

        Returns:
            DataFrame with top N reactions
        """
        if metric not in self.df.columns:
            logger.error(f"Metric '{metric}' not found. Run calculate_all_metrics() first.")
            return pd.DataFrame()

        ascending = metric in ['e_factor', 'pmi', 'energy_kwh', 'co2_kg']

        return self.df.nsmallest(n, metric) if ascending else self.df.nlargest(n, metric)

def test_calculator() -> Optional[pd.DataFrame]:
    """Test the metrics calculator"""
    from data_parser import ORDDataParser

    logger.info("Loading dataset...")
    parser = ORDDataParser('data/ord_search_results.pb')
    df = parser.parse_dataset()

    if df.empty:
        logger.error("No data to calculate metrics")
        return None

    calculator = GreenMetricsCalculator(df)
    df_with_metrics = calculator.calculate_all_metrics()

    print("\n" + "=" * 80)
    print("SAMPLE REACTIONS WITH METRICS")
    print("=" * 80)
    display_cols = [
        'reaction_id', 'yield_percent', 'atom_economy',
        'rme', 'e_factor', 'green_score',
    ]
    available_cols = [c for c in display_cols if c in df_with_metrics.columns]
    print(df_with_metrics[available_cols].head(10).to_string(index=False))

    print("\n" + "=" * 80)
    print("METRICS SUMMARY STATISTICS")
    print("=" * 80)
    print(calculator.get_summary_statistics().to_string())

    print("\n" + "=" * 80)
    print("TOP 5 GREENEST REACTIONS (by composite green score)")
    print("=" * 80)
    best = calculator.get_best_reactions(n=5, metric='green_score')
    if not best.empty:
        display_cols_best = [
            'reaction_id', 'yield_percent', 'green_score',
            'e_factor', 'solvent_score', 'catalyst',
        ]
        available_cols_best = [c for c in display_cols_best if c in best.columns]
        print(best[available_cols_best].to_string(index=False))

    return df_with_metrics

if __name__ == "__main__":
    test_calculator()