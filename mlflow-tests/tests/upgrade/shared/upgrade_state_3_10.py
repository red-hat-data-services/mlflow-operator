"""Shared MLflow upgrade scenario state for the 3.10 compatibility suite."""

from __future__ import annotations

EXPERIMENT_RUNS_STATE = {
    "experiment_name": "upgrade-exp-static-runs",
    "runs": [
        {
            "run_name": "upgrade-run-static-1",
            "params": {
                "optimizer": "adam",
                "learning_rate": "0.001",
                "batch_size": "32",
            },
            "metrics": {
                "loss": 0.125,
                "accuracy": 0.987,
            },
            "artifact_file": "run-1-summary.txt",
            "artifact_content": "static artifact content for run 1",
        },
        {
            "run_name": "upgrade-run-static-2",
            "params": {
                "optimizer": "sgd",
                "learning_rate": "0.010",
                "batch_size": "64",
            },
            "metrics": {
                "loss": 0.250,
                "accuracy": 0.975,
            },
            "artifact_file": "run-2-summary.txt",
            "artifact_content": "static artifact content for run 2",
        },
    ],
}

REGISTERED_MODELS_STATE = {
    "experiment_name": "upgrade-exp-static-models",
    "models": [
        {
            "name": "upgrade-registered-model-1",
            "versions": [
                {
                    "description": "upgrade model 1 version 1",
                    "run_name": "upgrade-model-1-run-1",
                },
                {
                    "description": "upgrade model 1 version 2",
                    "run_name": "upgrade-model-1-run-2",
                },
            ],
        },
        {
            "name": "upgrade-registered-model-2",
            "versions": [
                {
                    "description": "upgrade model 2 version 1",
                    "run_name": "upgrade-model-2-run-1",
                },
                {
                    "description": "upgrade model 2 version 2",
                    "run_name": "upgrade-model-2-run-2",
                },
            ],
        },
    ],
}
