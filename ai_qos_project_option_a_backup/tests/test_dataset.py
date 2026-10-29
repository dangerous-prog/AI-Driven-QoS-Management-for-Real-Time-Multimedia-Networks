"""
test_dataset.py
===============
Tests for dataset generation.
"""
import pytest
import os
import pandas as pd
import tempfile


class TestDatasetGeneration:
    def test_generates_dataframe(self):
        from dataset_generation import generate_dataset
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            df = generate_dataset(n_seeds_per_scenario=2, window_s=1.0,
                                  output_path=path, verbose=False)
            assert isinstance(df, pd.DataFrame)
            assert len(df) > 0
        finally:
            os.unlink(path)

    def test_csv_saved(self):
        from dataset_generation import generate_dataset
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            generate_dataset(n_seeds_per_scenario=2, window_s=1.0,
                             output_path=path, verbose=False)
            assert os.path.exists(path)
            df = pd.read_csv(path)
            assert len(df) > 0
        finally:
            os.unlink(path)

    def test_label_column_present(self):
        from dataset_generation import generate_dataset, LABEL_COLUMN
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            df = generate_dataset(n_seeds_per_scenario=2, window_s=1.0,
                                  output_path=path, verbose=False)
            assert LABEL_COLUMN in df.columns
        finally:
            os.unlink(path)

    def test_valid_labels_only(self):
        from dataset_generation import generate_dataset, LABEL_COLUMN
        import config
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            df = generate_dataset(n_seeds_per_scenario=2, window_s=1.0,
                                  output_path=path, verbose=False)
            invalid = df[~df[LABEL_COLUMN].isin(config.CONGESTION_LABELS)]
            assert len(invalid) == 0, f"Found invalid labels: {invalid[LABEL_COLUMN].unique()}"
        finally:
            os.unlink(path)

    def test_feature_label_lengths_match(self):
        from dataset_generation import generate_dataset, FEATURE_COLUMNS, LABEL_COLUMN
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            df = generate_dataset(n_seeds_per_scenario=2, window_s=1.0,
                                  output_path=path, verbose=False)
            assert len(df[FEATURE_COLUMNS]) == len(df[LABEL_COLUMN])
        finally:
            os.unlink(path)

    def test_no_nan_in_features(self):
        from dataset_generation import generate_dataset, FEATURE_COLUMNS
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            df = generate_dataset(n_seeds_per_scenario=2, window_s=1.0,
                                  output_path=path, verbose=False)
            assert not df[FEATURE_COLUMNS].isnull().any().any(), \
                "NaN values found in features"
        finally:
            os.unlink(path)

    def test_label_not_in_features(self):
        from dataset_generation import FEATURE_COLUMNS, LABEL_COLUMN
        assert LABEL_COLUMN not in FEATURE_COLUMNS, \
            "Label column leaked into feature list"

    def test_utilisation_not_in_features(self):
        from dataset_generation import FEATURE_COLUMNS
        assert "link_util_pct" not in FEATURE_COLUMNS, \
            "link_util_pct (used to derive label) is in feature list — potential leakage"
