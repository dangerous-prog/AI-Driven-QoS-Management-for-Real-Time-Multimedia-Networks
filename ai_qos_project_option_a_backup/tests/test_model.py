"""
test_model.py
=============
Tests for model training and prediction.
"""
import pytest
import os
import tempfile
import json
import pandas as pd


@pytest.fixture(scope="module")
def tiny_dataset():
    """Generate a minimal dataset for model tests."""
    from dataset_generation import generate_dataset
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    df = generate_dataset(n_seeds_per_scenario=5, window_s=1.0,
                          output_path=path, verbose=False)
    yield path, df
    os.unlink(path)


class TestModelTraining:
    def test_trains_without_error(self, tiny_dataset):
        from train_model import train_and_evaluate
        path, _ = tiny_dataset
        with tempfile.TemporaryDirectory() as model_dir, \
             tempfile.TemporaryDirectory() as results_dir, \
             tempfile.TemporaryDirectory() as figures_dir:
            result = train_and_evaluate(
                dataset_path=path,
                model_dir=model_dir,
                results_dir=results_dir,
                figures_dir=figures_dir,
                verbose=False,
            )
            assert "rf_accuracy" in result
            assert 0.0 <= result["rf_accuracy"] <= 1.0

    def test_model_file_saved(self, tiny_dataset):
        from train_model import train_and_evaluate
        path, _ = tiny_dataset
        with tempfile.TemporaryDirectory() as model_dir, \
             tempfile.TemporaryDirectory() as results_dir, \
             tempfile.TemporaryDirectory() as figures_dir:
            train_and_evaluate(
                dataset_path=path,
                model_dir=model_dir,
                results_dir=results_dir,
                figures_dir=figures_dir,
                verbose=False,
            )
            model_file = os.path.join(model_dir, "rf_model.joblib")
            assert os.path.exists(model_file)

    def test_metadata_saved(self, tiny_dataset):
        from train_model import train_and_evaluate
        path, _ = tiny_dataset
        with tempfile.TemporaryDirectory() as model_dir, \
             tempfile.TemporaryDirectory() as results_dir, \
             tempfile.TemporaryDirectory() as figures_dir:
            train_and_evaluate(
                dataset_path=path,
                model_dir=model_dir,
                results_dir=results_dir,
                figures_dir=figures_dir,
                verbose=False,
            )
            meta_file = os.path.join(model_dir, "model_metadata.json")
            assert os.path.exists(meta_file)
            with open(meta_file) as f:
                meta = json.load(f)
            assert "feature_columns" in meta
            assert "congestion_labels" in meta

    def test_rf_beats_dummy(self, tiny_dataset):
        """Random Forest accuracy should be >= DummyClassifier accuracy."""
        from train_model import train_and_evaluate
        path, _ = tiny_dataset
        with tempfile.TemporaryDirectory() as model_dir, \
             tempfile.TemporaryDirectory() as results_dir, \
             tempfile.TemporaryDirectory() as figures_dir:
            r = train_and_evaluate(
                dataset_path=path,
                model_dir=model_dir,
                results_dir=results_dir,
                figures_dir=figures_dir,
                verbose=False,
            )
            assert r["rf_accuracy"] >= r["dummy_accuracy"]

    def test_confusion_matrix_saved(self, tiny_dataset):
        from train_model import train_and_evaluate
        path, _ = tiny_dataset
        with tempfile.TemporaryDirectory() as model_dir, \
             tempfile.TemporaryDirectory() as results_dir, \
             tempfile.TemporaryDirectory() as figures_dir:
            train_and_evaluate(
                dataset_path=path,
                model_dir=model_dir,
                results_dir=results_dir,
                figures_dir=figures_dir,
                verbose=False,
            )
            cm_file = os.path.join(figures_dir, "confusion_matrix.png")
            assert os.path.exists(cm_file)

    def test_prediction_returns_valid_class(self, tiny_dataset):
        """Prediction should return one of the documented congestion labels."""
        from train_model import train_and_evaluate
        from predict_congestion import predict_from_simulation
        from traffic_simulation import run_simulation
        import config, joblib, json

        path, _ = tiny_dataset
        with tempfile.TemporaryDirectory() as model_dir, \
             tempfile.TemporaryDirectory() as results_dir, \
             tempfile.TemporaryDirectory() as figures_dir:
            r = train_and_evaluate(
                dataset_path=path,
                model_dir=model_dir,
                results_dir=results_dir,
                figures_dir=figures_dir,
                verbose=False,
            )
            model = joblib.load(r["model_path"])
            with open(os.path.join(model_dir, "model_metadata.json")) as f:
                metadata = json.load(f)
            sim_result = run_simulation(scheduler="fifo", load_scenario="medium", duration_s=5.0)
            pred = predict_from_simulation(
                sim_result,
                load_multiplier=config.LOAD_SCENARIOS["medium"]["multiplier"],
                model=model,
                metadata=metadata,
            )
            assert pred["predicted_class"] in config.CONGESTION_LABELS
