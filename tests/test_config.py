from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ffmodel.config import (
    ProjectConfig,
    load_league_config,
    load_model_config,
    load_project_config,
    load_ranking_config,
    load_scoring_config,
    load_sources_config,
)


class TestScoringConfig:
    def test_loads_offense(self, configs_dir: Path) -> None:
        cfg = load_scoring_config(configs_dir / "scoring.yaml")
        assert cfg.offense.passing_td == 4.0
        assert cfg.offense.interception == -2.0
        assert cfg.offense.reception == 0.5
        assert cfg.offense.rushing_td == 6.0

    def test_loads_kicker(self, configs_dir: Path) -> None:
        cfg = load_scoring_config(configs_dir / "scoring.yaml")
        assert cfg.kicker.fg_50_plus == 5.0
        assert cfg.kicker.pat_made == 1.0

    def test_loads_dst_brackets(self, configs_dir: Path) -> None:
        cfg = load_scoring_config(configs_dir / "scoring.yaml")
        assert len(cfg.dst.points_allowed_brackets) == 7
        assert cfg.dst.points_allowed_brackets[0] == (0, 0, 10.0)
        assert cfg.dst.points_allowed_brackets[-1] == (35, 999, -4.0)

    def test_is_frozen(self, configs_dir: Path) -> None:
        cfg = load_scoring_config(configs_dir / "scoring.yaml")
        with pytest.raises(FrozenInstanceError):
            cfg.offense.passing_td = 6.0  # type: ignore[misc]


class TestLeagueConfig:
    def test_loads_league(self, configs_dir: Path) -> None:
        cfg = load_league_config(configs_dir / "league.yaml")
        assert cfg.league_id == 1221676
        assert cfg.league_name == "STOP!"
        assert cfg.teams == 10
        assert cfg.roster_slots["QB"] == 2
        assert cfg.roster_slots["BN"] == 6
        assert cfg.flex_eligible == ("RB", "WR", "TE")

    def test_draft_and_playoffs(self, configs_dir: Path) -> None:
        cfg = load_league_config(configs_dir / "league.yaml")
        assert cfg.draft.date == "2026-09-01"
        assert cfg.playoffs.weeks == (15, 16, 17)

    def test_is_frozen(self, configs_dir: Path) -> None:
        cfg = load_league_config(configs_dir / "league.yaml")
        with pytest.raises(FrozenInstanceError):
            cfg.teams = 12  # type: ignore[misc]


class TestModelConfig:
    def test_loads_recency_weights(self, configs_dir: Path) -> None:
        cfg = load_model_config(configs_dir / "model.yaml")
        assert cfg.recency_weights == {1: 0.50, 2: 0.30, 3: 0.20}
        assert sum(cfg.recency_weights.values()) == pytest.approx(1.0)

    def test_loads_regression_samples(self, configs_dir: Path) -> None:
        cfg = load_model_config(configs_dir / "model.yaml")
        assert cfg.regression_samples["pass_td_rate"] == 1500
        assert cfg.regression_samples["int_rate"] == 800

    def test_loads_games_active(self, configs_dir: Path) -> None:
        cfg = load_model_config(configs_dir / "model.yaml")
        assert cfg.games_active.default_max == 17
        assert cfg.games_active.position_prior["RB"] == 14.5

    def test_loads_overlay(self, configs_dir: Path) -> None:
        cfg = load_model_config(configs_dir / "model.yaml")
        assert cfg.overlay.max_effect_per_factor == 0.15
        assert cfg.overlay.max_total_effect == 0.25
        assert cfg.overlay.low_confidence_threshold == 0.30

    def test_loads_uncertainty(self, configs_dir: Path) -> None:
        cfg = load_model_config(configs_dir / "model.yaml")
        assert cfg.uncertainty.method == "bootstrap_residual"
        assert cfg.uncertainty.n_samples == 5000
        assert cfg.uncertainty.percentiles == (25, 50, 75)

    def test_is_frozen(self, configs_dir: Path) -> None:
        cfg = load_model_config(configs_dir / "model.yaml")
        with pytest.raises(FrozenInstanceError):
            cfg.uncertainty.n_samples = 1000  # type: ignore[misc]


class TestRankingConfig:
    def test_loads_ranking(self, configs_dir: Path) -> None:
        cfg = load_ranking_config(configs_dir / "ranking.yaml")
        assert cfg.ranking_objective == "median"
        assert cfg.replacement_level["QB"] == 20
        assert cfg.vor_method == "simple"


class TestSourcesConfig:
    def test_loads_sources(self, configs_dir: Path) -> None:
        cfg = load_sources_config(configs_dir / "sources.yaml")
        assert cfg.seasons.min == 2020
        assert cfg.seasons.max == 2025
        assert cfg.seasons.target == 2026
        assert "pbp" in cfg.required
        assert "nextgen_passing" in cfg.optional
        assert cfg.fallback_behavior.required_missing == "fail"


class TestProjectConfig:
    def test_loads_all(self, configs_dir: Path) -> None:
        cfg = load_project_config(configs_dir)
        assert isinstance(cfg, ProjectConfig)
        assert cfg.scoring.offense.passing_td == 4.0
        assert cfg.league.teams == 10
        assert cfg.model.recency_weights[1] == 0.50
        assert cfg.ranking.ranking_objective == "median"
        assert "pbp" in cfg.sources.required

    def test_config_hash_deterministic(self, configs_dir: Path) -> None:
        cfg1 = load_project_config(configs_dir)
        cfg2 = load_project_config(configs_dir)
        assert cfg1.config_hash == cfg2.config_hash
        assert len(cfg1.config_hash) == 64  # SHA-256 hex

    def test_config_hash_is_hex(self, configs_dir: Path) -> None:
        cfg = load_project_config(configs_dir)
        int(cfg.config_hash, 16)  # raises ValueError if not valid hex

    def test_missing_dir_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_project_config("/nonexistent/path")

    def test_is_frozen(self, configs_dir: Path) -> None:
        cfg = load_project_config(configs_dir)
        with pytest.raises(FrozenInstanceError):
            cfg.config_hash = "abc"  # type: ignore[misc]
