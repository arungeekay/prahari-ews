"""Shared pytest fixtures for the datagen acceptance suite.

The dataset is generated once per session (seed 42) and reused across tests - generation is
deterministic, so every test sees the same synthetic Bharat.
"""

from __future__ import annotations

import pytest

from core.datagen import generate


@pytest.fixture(scope="session")
def frames():
    """The canonical seed-42 dataset as {table: DataFrame}."""
    return generate(seed=42)


@pytest.fixture(scope="session")
def borrowers(frames):
    return frames["borrowers"]


@pytest.fixture(scope="session")
def msme_monthly(frames):
    return frames["msme_monthly"]


@pytest.fixture(scope="session")
def customers(frames):
    return frames["customers"]


@pytest.fixture(scope="session")
def retail_monthly(frames):
    return frames["retail_monthly"]


@pytest.fixture(scope="session")
def engagement(frames):
    return frames["retail_engagement"]
