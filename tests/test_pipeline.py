"""Tests for pipeline orchestrator and export writer."""

import json
from pathlib import Path

import pandas as pd
import pytest

from ffmodel.export.writer import OUTPUT_SCHEMA, write_outputs
from ffmodel.overlay.applicator import OverlayResult
from ffmodel.pipeline import generate_run_id
from ffmodel.ranking.ranker import RankedPlayer, compute_rankings, rankings_to_dataframe


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_ranked():
    return [
        RankedPlayer(
            player_id="QB1", position="QB", total_points=300.0,
            model_only_points=300.0, overlay_adjusted_points=300.0,
            overlay_delta=0.0, combined_multiplier=1.0, manual_heavy=False,
            factors_applied=0, position_rank=1, overall_rank=1, vor=50.0,
            games_active=16.0, is_rookie=False, is_team_changer=False,
        ),
        RankedPlayer(
            player_id="RB1", position="RB", total_points=280.0,
            model_only_points=280.0, overlay_adjusted_points=280.0,
            overlay_delta=0.0, combined_multiplier=1.0, manual_heavy=False,
            factors_applied=0, position_rank=1, overall_rank=2, vor=60.0,
            games_active=15.0, is_rookie=False, is_team_changer=False,
        ),
        RankedPlayer(
            player_id="DEF1", position="DEF", total_points=120.0,
            model_only_points=120.0, overlay_adjusted_points=120.0,
            overlay_delta=0.0, combined_multiplier=1.0, manual_heavy=False,
            factors_applied=0, position_rank=1, overall_rank=3, vor=0.0,
            games_active=17.0, is_rookie=False, is_team_changer=False,
        ),
        RankedPlayer(
            player_id="K1", position="K", total_points=130.0,
            model_only_points=130.0, overlay_adjusted_points=130.0,
            overlay_delta=0.0, combined_multiplier=1.0, manual_heavy=False,
            factors_applied=0, position_rank=1, overall_rank=4, vor=0.0,
            games_active=17.0, is_rookie=False, is_team_changer=False,
        ),
    ]


# ---------------------------------------------------------------------------
# Tests: generate_run_id
# ---------------------------------------------------------------------------

class TestGenerateRunId:
    def test_format(self):
        run_id = generate_run_id("2025-09-01", "abcdef1234567890")
        assert run_id.startswith("2025-09-01_")
        assert run_id.endswith("_abcdef12")

    def test_config_hash_truncated(self):
        run_id = generate_run_id("2025-09-01", "1234567890abcdef")
        parts = run_id.split("_")
        assert parts[-1] == "12345678"


# ---------------------------------------------------------------------------
# Tests: write_outputs
# ---------------------------------------------------------------------------

class TestWriteOutputs:
    def test_creates_all_files(self, tmp_path, sample_ranked):
        run_dir = write_outputs(
            sample_ranked, "test_run_001", "2025-09-01",
            "abc123", output_base=tmp_path,
        )

        rankings_dir = run_dir / "rankings"
        projections_dir = run_dir / "projections"

        assert (rankings_dir / "player_projection.csv").exists()
        assert (rankings_dir / "player_projection.parquet").exists()
        assert (rankings_dir / "dst_projection.csv").exists()
        assert (rankings_dir / "dst_projection.parquet").exists()
        assert (rankings_dir / "kicker_projection.csv").exists()
        assert (rankings_dir / "kicker_projection.parquet").exists()
        assert (rankings_dir / "combined_rankings.csv").exists()
        assert (rankings_dir / "schema.json").exists()
        assert (projections_dir / "projection_run_fact.parquet").exists()

    def test_combined_rankings_contains_all_positions(self, tmp_path, sample_ranked):
        write_outputs(
            sample_ranked, "test_run_001", "2025-09-01",
            "abc123", output_base=tmp_path,
        )
        combined = pd.read_csv(tmp_path / "test_run_001" / "rankings" / "combined_rankings.csv")
        positions = set(combined["position"].unique())
        assert positions == {"QB", "RB", "DEF", "K"}

    def test_player_projection_excludes_dst_and_kicker(self, tmp_path, sample_ranked):
        write_outputs(
            sample_ranked, "test_run_001", "2025-09-01",
            "abc123", output_base=tmp_path,
        )
        player_df = pd.read_csv(tmp_path / "test_run_001" / "rankings" / "player_projection.csv")
        assert set(player_df["position"].unique()) == {"QB", "RB"}

    def test_dst_projection_only_def(self, tmp_path, sample_ranked):
        write_outputs(
            sample_ranked, "test_run_001", "2025-09-01",
            "abc123", output_base=tmp_path,
        )
        dst_df = pd.read_csv(tmp_path / "test_run_001" / "rankings" / "dst_projection.csv")
        assert set(dst_df["position"].unique()) == {"DEF"}

    def test_schema_json_valid(self, tmp_path, sample_ranked):
        write_outputs(
            sample_ranked, "test_run_001", "2025-09-01",
            "abc123", output_base=tmp_path,
        )
        schema_path = tmp_path / "test_run_001" / "rankings" / "schema.json"
        with open(schema_path) as f:
            schema = json.load(f)
        assert "player_id" in schema
        assert "overall_rank" in schema
        assert schema == OUTPUT_SCHEMA

    def test_projection_run_fact_metadata(self, tmp_path, sample_ranked):
        write_outputs(
            sample_ranked, "test_run_001", "2025-09-01",
            "abc123", output_base=tmp_path,
        )
        run_fact = pd.read_parquet(
            tmp_path / "test_run_001" / "projections" / "projection_run_fact.parquet"
        )
        assert len(run_fact) == 1
        row = run_fact.iloc[0]
        assert row["run_id"] == "test_run_001"
        assert row["as_of_date"] == "2025-09-01"
        assert row["config_hash"] == "abc123"
        assert row["total_players_ranked"] == 4

    def test_overlay_delta_zero_for_no_factors(self, tmp_path, sample_ranked):
        write_outputs(
            sample_ranked, "test_run_001", "2025-09-01",
            "abc123", output_base=tmp_path,
        )
        combined = pd.read_csv(tmp_path / "test_run_001" / "rankings" / "combined_rankings.csv")
        assert (combined["overlay_delta"] == 0.0).all()

    def test_overall_rank_starts_at_one(self, tmp_path, sample_ranked):
        write_outputs(
            sample_ranked, "test_run_001", "2025-09-01",
            "abc123", output_base=tmp_path,
        )
        combined = pd.read_csv(tmp_path / "test_run_001" / "rankings" / "combined_rankings.csv")
        assert combined["overall_rank"].min() == 1


# ---------------------------------------------------------------------------
# Tests: CLI integration (rank and run commands parse)
# ---------------------------------------------------------------------------

class TestCLIParsing:
    def test_rank_command_exists(self):
        from ffmodel.cli import main
        with pytest.raises(SystemExit):
            main(["rank", "--as-of-date", "2025-09-01", "--help"])

    def test_run_command_exists(self):
        from ffmodel.cli import main
        with pytest.raises(SystemExit):
            main(["run", "--as-of-date", "2025-09-01", "--help"])
