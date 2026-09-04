"""§3.5 Determinism: same seed → identical parquet checksums (and content)."""

from __future__ import annotations

from core.datagen import generate, content_hash, write_parquet, TABLES


def test_same_seed_identical_content(frames):
    """A second generation with the same seed reproduces every table byte-for-byte (logically)."""
    frames2 = generate(seed=42)
    for name in TABLES:
        assert content_hash(frames[name]) == content_hash(frames2[name]), f"{name} not deterministic"


def test_same_seed_identical_parquet_md5(frames, tmp_path):
    """Written parquet files have identical md5 across two runs (BUILD_SPEC §3.5, literal)."""
    frames2 = generate(seed=42)
    c1 = write_parquet(frames, tmp_path / "run1")
    c2 = write_parquet(frames2, tmp_path / "run2")
    for name in TABLES:
        assert c1[name]["md5"] == c2[name]["md5"], f"{name}.parquet md5 differs across runs"
        assert c1[name]["rows"] == c2[name]["rows"]


def test_different_seed_changes_data(frames):
    """A different seed must actually change the economy (guards against a constant generator)."""
    other = generate(seed=7)
    changed = sum(content_hash(frames[n]) != content_hash(other[n]) for n in TABLES)
    assert changed >= len(TABLES) - 1  # essentially everything should differ


def test_row_counts(frames):
    assert len(frames["borrowers"]) == 3000
    assert len(frames["customers"]) == 10000
    assert len(frames["anchors"]) == 4
