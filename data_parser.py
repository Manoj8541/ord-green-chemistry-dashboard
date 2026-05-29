"""
Data Parser Module for Green Chemistry Dashboard
Handles parsing of ORD .pb files and converts to pandas DataFrame
"""

import math
import logging
import os
import traceback
from typing import List, Optional, Any

import pandas as pd
from ord_schema.proto import reaction_pb2, dataset_pb2
from google.protobuf.internal.decoder import _DecodeVarint32
from google.protobuf.internal.wire_format import WIRETYPE_LENGTH_DELIMITED

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class ORDDataParser:
    """Parser for Open Reaction Database Protocol Buffer files"""

    def __init__(self, file_path: str):
        """
        Initialize the ORD data parser.

        Args:
            file_path: Path to the .pb file containing ORD reactions
        """
        self.file_path = file_path
        self.reactions: List[reaction_pb2.Reaction] = []
        self._validate_file_path()

    def _validate_file_path(self) -> None:
        """Validate the input file path"""
        if not self.file_path:
            raise ValueError("File path cannot be empty")

        if not self.file_path.endswith('.pb'):
            logger.warning(
                f"File '{self.file_path}' doesn't have .pb extension. "
                "Attempting to parse anyway..."
            )

    def load_dataset(self) -> bool:
        """
        Load and parse the .pb file containing ORD reactions.

        Returns:
            bool: True if reactions were successfully loaded, False otherwise
        """
        logger.info(f"Loading: {self.file_path}")

        if not os.path.exists(self.file_path):
            logger.error(f"File not found: {self.file_path}")
            return False

        if not os.path.isfile(self.file_path):
            logger.error(f"Path is not a file: {self.file_path}")
            return False

        try:
            with open(self.file_path, 'rb') as f:
                data = f.read()

            data_len = len(data)

            if data_len == 0:
                logger.error("File is empty")
                return False

            # Method 1: Try to parse as standard Dataset message first
            try:
                dataset = dataset_pb2.Dataset()
                dataset.ParseFromString(data)
                if dataset.reactions:
                    self.reactions = list(dataset.reactions)
                    logger.info(f"✓ Loaded {len(self.reactions)} reactions (Dataset format)")
                    return True
            except Exception as e:
                logger.debug(f"Not a Dataset format: {e}")

            # Method 2: Parse as wrapper with repeated Reaction messages
            pos = 0
            reactions_found = 0

            while pos < data_len:
                try:
                    if pos >= data_len:
                        break

                    tag_byte = data[pos]
                    pos += 1

                    field_number = tag_byte >> 3
                    wire_type = tag_byte & 0x07

                    # Only process length-delimited fields
                    if wire_type != WIRETYPE_LENGTH_DELIMITED:
                        if wire_type == 0:  # Varint
                            varint_count = 0
                            while pos < data_len and (data[pos] & 0x80) and varint_count < 10:
                                pos += 1
                                varint_count += 1
                            if pos < data_len:
                                pos += 1
                        elif wire_type == 1:  # 64-bit
                            pos = min(pos + 8, data_len)
                        elif wire_type == 5:  # 32-bit
                            pos = min(pos + 4, data_len)
                        continue

                    if pos >= data_len:
                        break

                    try:
                        msg_len, new_pos = _DecodeVarint32(data, pos)
                    except (IndexError, ValueError) as e:
                        logger.debug(f"Error decoding varint at position {pos}: {e}")
                        break

                    pos = new_pos

                    if pos + msg_len > data_len:
                        logger.warning(f"Message length {msg_len} exceeds remaining data")
                        break

                    msg_bytes = data[pos:pos + msg_len]
                    pos += msg_len

                    # Field 1 is typically the dataset name/title, skip it
                    if field_number == 1:
                        continue

                    # Try to parse as Reaction
                    try:
                        reaction = reaction_pb2.Reaction()
                        reaction.ParseFromString(msg_bytes)

                        if reaction.inputs or reaction.outcomes:
                            self.reactions.append(reaction)
                            reactions_found += 1
                    except Exception as parse_error:
                        logger.debug(f"Could not parse as reaction: {parse_error}")
                        continue

                except Exception as e:
                    logger.debug(f"Error at position {pos}: {e}")
                    break

            if self.reactions:
                logger.info(f"✓ Loaded {len(self.reactions)} reactions (wrapper format)")
                return True

            logger.error("No reactions found in file")
            return False

        except FileNotFoundError:
            logger.error(f"File not found: {self.file_path}")
            return False
        except PermissionError:
            logger.error(f"Permission denied: {self.file_path}")
            return False
        except Exception as e:
            logger.error(f"Error loading dataset: {e}")
            traceback.print_exc()
            return False

    def _get_identifier_value(
        self, identifiers: Any, preferred_types: Optional[List[int]] = None
    ) -> str:
        """
        Extract best identifier value from a list of identifiers.

        Args:
            identifiers: List of CompoundIdentifier objects
            preferred_types: Optional list of preferred identifier types

        Returns:
            str: The identifier value or 'Unknown'
        """
        if not identifiers:
            return 'Unknown'

        if preferred_types is None:
            preferred_types = [
                reaction_pb2.CompoundIdentifier.NAME,
                reaction_pb2.CompoundIdentifier.SMILES,
                reaction_pb2.CompoundIdentifier.INCHI,
            ]

        for pref_type in preferred_types:
            for identifier in identifiers:
                if identifier.type == pref_type and identifier.value:
                    value = identifier.value.strip()
                    if value:
                        return value

        for identifier in identifiers:
            if identifier.value:
                value = identifier.value.strip()
                if value:
                    return value

        return 'Unknown'

    def _validate_numeric(self, value: Optional[float]) -> Optional[float]:
        """
        Validate numeric value (check for NaN, infinity).

        Args:
            value: Numeric value to validate

        Returns:
            Validated value or None if invalid
        """
        if value is None:
            return None

        if math.isnan(value) or math.isinf(value):
            return None

        return value

    def _convert_time_to_hours(self, time_obj: Any) -> Optional[float]:
        """
        Convert ORD Time message to hours with proper unit handling.

        Args:
            time_obj: ORD Time message object

        Returns:
            Time in hours or None if invalid
        """
        if time_obj is None:
            return None

        value = time_obj.value
        if value is None or value == 0:
            return None

        value = self._validate_numeric(value)
        if value is None:
            return None

        units = time_obj.units

        if units == reaction_pb2.Time.SECOND:
            return value / 3600.0
        elif units == reaction_pb2.Time.MINUTE:
            return value / 60.0
        elif units == reaction_pb2.Time.HOUR:
            return value
        elif units == reaction_pb2.Time.DAY:
            return value * 24.0
        else:
            logger.debug(f"Unspecified time unit, assuming hours for value {value}")
            return value

    def _convert_temperature_to_celsius(self, temp_obj: Any) -> Optional[float]:
        """
        Convert ORD Temperature message to Celsius with proper unit handling.

        Args:
            temp_obj: ORD Temperature message object

        Returns:
            Temperature in Celsius or None if invalid
        """
        if temp_obj is None:
            return None

        value = temp_obj.value
        if value is None:
            return None

        value = self._validate_numeric(value)
        if value is None:
            return None

        units = temp_obj.units

        if units == reaction_pb2.Temperature.CELSIUS:
            return value
        elif units == reaction_pb2.Temperature.FAHRENHEIT:
            return (value - 32.0) * 5.0 / 9.0
        elif units == reaction_pb2.Temperature.KELVIN:
            return value - 273.15
        else:
            logger.debug(f"Unspecified temperature unit, assuming Celsius for value {value}")
            return value

    def extract_reaction_data(self, show_progress: bool = True) -> pd.DataFrame:
        """
        Extract relevant data from reactions into structured format.

        Args:
            show_progress: Whether to show progress for large datasets

        Returns:
            DataFrame containing extracted reaction data
        """
        reaction_data: List[dict] = []
        total = len(self.reactions)

        for idx, reaction in enumerate(self.reactions):
            if show_progress and total > 100 and (idx + 1) % 100 == 0:
                logger.info(f"Processing reaction {idx + 1}/{total}...")

            try:
                rxn_id = reaction.reaction_id if reaction.reaction_id else f"rxn_{idx:04d}"

                record: dict = {
                    'reaction_id': rxn_id,
                    'temperature_c': None,
                    'reaction_time_h': None,
                    'solvent': None,
                    'catalyst': None,
                    'yield_percent': None,
                    'reactant_1': None,
                    'reactant_2': None,
                    'product': None,
                }

                # Extract temperature from conditions
                try:
                    temp_conditions = reaction.conditions.temperature
                    if temp_conditions.HasField('setpoint'):
                        record['temperature_c'] = self._convert_temperature_to_celsius(
                            temp_conditions.setpoint
                        )
                    elif temp_conditions.HasField('control'):
                        if temp_conditions.control.HasField('setpoint'):
                            record['temperature_c'] = self._convert_temperature_to_celsius(
                                temp_conditions.control.setpoint
                            )
                except (AttributeError, ValueError) as e:
                    logger.debug(f"Could not extract temperature for {rxn_id}: {e}")

                # Extract reaction time from outcomes
                try:
                    for outcome in reaction.outcomes:
                        if outcome.HasField('reaction_time'):
                            record['reaction_time_h'] = self._convert_time_to_hours(
                                outcome.reaction_time
                            )
                            if record['reaction_time_h'] is not None:
                                break
                except (AttributeError, ValueError) as e:
                    logger.debug(f"Could not extract reaction time for {rxn_id}: {e}")

                # Fallback: try stirring duration
                if record['reaction_time_h'] is None:
                    try:
                        stirring = reaction.conditions.stirring
                        if stirring.HasField('duration'):
                            record['reaction_time_h'] = self._convert_time_to_hours(
                                stirring.duration
                            )
                    except (AttributeError, ValueError):
                        pass

                # Extract components from inputs
                try:
                    for _key, reaction_input in reaction.inputs.items():
                        for component in reaction_input.components:
                            comp_name = self._get_identifier_value(component.identifiers)
                            role = component.reaction_role

                            if role == reaction_pb2.ReactionRole.REACTANT:
                                if record['reactant_1'] is None:
                                    record['reactant_1'] = comp_name
                                elif record['reactant_2'] is None:
                                    record['reactant_2'] = comp_name

                            elif role == reaction_pb2.ReactionRole.CATALYST:
                                if record['catalyst'] is None:
                                    record['catalyst'] = comp_name
                                else:
                                    record['catalyst'] += f"; {comp_name}"

                            elif role == reaction_pb2.ReactionRole.SOLVENT:
                                if record['solvent'] is None:
                                    record['solvent'] = comp_name
                                else:
                                    record['solvent'] += f"; {comp_name}"
                except (AttributeError, KeyError, TypeError) as e:
                    logger.debug(f"Could not extract inputs for {rxn_id}: {e}")

                # Extract products and yield
                try:
                    if reaction.outcomes:
                        outcome = reaction.outcomes[0]
                        if outcome.products:
                            product = outcome.products[0]

                            record['product'] = self._get_identifier_value(
                                product.identifiers
                            )

                            for measurement in product.measurements:
                                if measurement.type == reaction_pb2.ProductMeasurement.YIELD:
                                    if measurement.HasField('percentage'):
                                        yield_val = measurement.percentage.value
                                        yield_val = self._validate_numeric(yield_val)
                                        if yield_val is not None and 0 <= yield_val <= 100:
                                            record['yield_percent'] = yield_val
                                        break
                except (AttributeError, IndexError, TypeError) as e:
                    logger.debug(f"Could not extract products for {rxn_id}: {e}")

                reaction_data.append(record)

            except Exception as e:
                logger.warning(f"Error processing reaction {idx}: {e}")
                continue

        return pd.DataFrame(reaction_data)

    def parse_dataset(
        self,
        remove_invalid_yield: bool = True,
        min_yield: float = 0.0,
        show_progress: bool = True,
    ) -> pd.DataFrame:
        """
        Main method to parse dataset and return DataFrame.

        Args:
            remove_invalid_yield: Whether to remove reactions without valid yield
            min_yield: Minimum yield threshold (default 0.0)
            show_progress: Whether to show progress for large datasets

        Returns:
            DataFrame containing parsed reaction data
        """
        if not self.load_dataset():
            logger.error("Failed to load dataset")
            return pd.DataFrame()

        df = self.extract_reaction_data(show_progress=show_progress)

        logger.info(f"✓ Extracted {len(df)} reaction records")

        if remove_invalid_yield:
            initial_count = len(df)
            df = df.dropna(subset=['yield_percent'])
            df = df[df['yield_percent'] > min_yield]

            removed = initial_count - len(df)
            if removed > 0:
                logger.info(
                    f"  Removed {removed} reactions without valid yield data "
                    f"(min_yield={min_yield}%)"
                )

        logger.info(f"✓ Final dataset: {len(df)} reactions")

        if len(df) > 0:
            logger.info(f"✓ Columns: {', '.join(df.columns)}")
        else:
            logger.warning("No reactions remaining after filtering")

        return df


def test_parser(file_path: str = 'data/ord_search_results.pb') -> pd.DataFrame:
    """
    Test the parser with sample data.

    Args:
        file_path: Path to the ORD dataset file

    Returns:
        DataFrame containing parsed reactions
    """
    try:
        parser = ORDDataParser(file_path)
        df = parser.parse_dataset()

        if not df.empty:
            print("\n" + "=" * 70)
            print("SAMPLE DATA (First 5 reactions)")
            print("=" * 70)
            print(df.head().to_string())

            print("\n" + "=" * 70)
            print("DATASET STATISTICS")
            print("=" * 70)
            print(f"Total reactions: {len(df)}")
            print("\nData completeness:")
            for col in df.columns:
                non_null = df[col].notna().sum()
                percentage = (non_null / len(df)) * 100
                print(f"  {col}: {non_null}/{len(df)} ({percentage:.1f}%)")

            if df['yield_percent'].notna().any():
                print("\nYield Statistics:")
                print(f"  Range: {df['yield_percent'].min():.1f}% to {df['yield_percent'].max():.1f}%")
                print(f"  Mean: {df['yield_percent'].mean():.1f}%")
                print(f"  Median: {df['yield_percent'].median():.1f}%")

            if df['temperature_c'].notna().any():
                temp_valid = df['temperature_c'].dropna()
                print("\nTemperature Statistics:")
                print(f"  Range: {temp_valid.min():.1f}°C to {temp_valid.max():.1f}°C")
                print(f"  Mean: {temp_valid.mean():.1f}°C")

            if df['reaction_time_h'].notna().any():
                time_valid = df['reaction_time_h'].dropna()
                print("\nReaction Time Statistics:")
                print(f"  Range: {time_valid.min():.2f}h to {time_valid.max():.2f}h")
                print(f"  Mean: {time_valid.mean():.2f}h")

            if df['solvent'].notna().any():
                print("\nTop 5 Solvents:")
                print(df['solvent'].value_counts().head().to_string())

            if df['catalyst'].notna().any():
                print("\nTop 5 Catalysts:")
                print(df['catalyst'].value_counts().head().to_string())

        else:
            print("\n✗ No valid reaction data found in dataset")

        return df

    except Exception as e:
        logger.error(f"Test failed: {e}")
        traceback.print_exc()
        return pd.DataFrame()


if __name__ == "__main__":
    test_parser()