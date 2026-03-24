from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Frozen dataclasses — one per config file
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OffenseScoringConfig:
    passing_yards_per_point: float
    passing_td: float
    interception: float
    rushing_yards_per_point: float
    rushing_td: float
    reception: float
    receiving_yards_per_point: float
    receiving_td: float
    return_td: float
    two_pt_conversion: float
    fumble_lost: float
    offensive_fumble_return_td: float


@dataclass(frozen=True)
class KickerScoringConfig:
    fg_0_19: float
    fg_20_29: float
    fg_30_39: float
    fg_40_49: float
    fg_50_plus: float
    pat_made: float


@dataclass(frozen=True)
class DSTScoringConfig:
    sack: float
    interception: float
    fumble_recovery: float
    touchdown: float
    safety: float
    block_kick: float
    return_td: float
    extra_point_return: float
    points_allowed_brackets: tuple[tuple[int, int, float], ...]


@dataclass(frozen=True)
class ScoringConfig:
    offense: OffenseScoringConfig
    kicker: KickerScoringConfig
    dst: DSTScoringConfig


@dataclass(frozen=True)
class DraftConfig:
    type: str
    date: str
    pick_time_seconds: int


@dataclass(frozen=True)
class PlayoffConfig:
    teams: int
    weeks: tuple[int, ...]
    tie_breaker: str
    reseeding: bool
    seeding: str


@dataclass(frozen=True)
class WaiverConfig:
    type: str
    time_days: int
    weekly_deadline: str


@dataclass(frozen=True)
class LeagueConfig:
    league_id: int
    league_name: str
    platform: str
    teams: int
    divisions: int
    scoring_type: str
    fractional_points: bool
    negative_points: bool
    roster_slots: dict[str, int]
    flex_eligible: tuple[str, ...]
    draft: DraftConfig
    playoffs: PlayoffConfig
    waiver: WaiverConfig


@dataclass(frozen=True)
class GamesActiveConfig:
    default_max: int
    shrinkage: float
    position_prior: dict[str, float]
    low_sample_threshold: int


@dataclass(frozen=True)
class OverlayConfig:
    enabled: bool
    max_effect_per_factor: float
    max_total_effect: float
    low_confidence_threshold: float


@dataclass(frozen=True)
class UncertaintyConfig:
    method: str
    n_samples: int
    percentiles: tuple[int, ...]


@dataclass(frozen=True)
class TeamChangerConfig:
    player_history_weight: float
    team_prior_weight: float


@dataclass(frozen=True)
class RookieConfig:
    draft_round_buckets: tuple[str, ...]


@dataclass(frozen=True)
class ModelConfig:
    recency_weights: dict[int, float]
    regression_samples: dict[str, int]
    games_active: GamesActiveConfig
    overlay: OverlayConfig
    uncertainty: UncertaintyConfig
    team_changer: TeamChangerConfig
    rookie: RookieConfig


@dataclass(frozen=True)
class RankingConfig:
    ranking_objective: str
    replacement_level: dict[str, int]
    vor_method: str


@dataclass(frozen=True)
class SeasonsConfig:
    min: int
    max: int
    target: int


@dataclass(frozen=True)
class FallbackConfig:
    optional_missing: str
    required_missing: str


@dataclass(frozen=True)
class SourcesConfig:
    seasons: SeasonsConfig
    required: tuple[str, ...]
    optional: tuple[str, ...]
    fallback_behavior: FallbackConfig


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_scoring_config(path: Path) -> ScoringConfig:
    raw = _load_yaml(path)
    offense = OffenseScoringConfig(**raw["offense"])
    kicker = KickerScoringConfig(**raw["kicker"])
    dst_raw = dict(raw["dst"])
    dst_raw["points_allowed_brackets"] = tuple(
        tuple(b) for b in dst_raw["points_allowed_brackets"]
    )
    dst = DSTScoringConfig(**dst_raw)
    return ScoringConfig(offense=offense, kicker=kicker, dst=dst)


def load_league_config(path: Path) -> LeagueConfig:
    raw = _load_yaml(path)
    return LeagueConfig(
        league_id=raw["league_id"],
        league_name=raw["league_name"],
        platform=raw["platform"],
        teams=raw["teams"],
        divisions=raw["divisions"],
        scoring_type=raw["scoring_type"],
        fractional_points=raw["fractional_points"],
        negative_points=raw["negative_points"],
        roster_slots=raw["roster_slots"],
        flex_eligible=tuple(raw["flex_eligible"]),
        draft=DraftConfig(**raw["draft"]),
        playoffs=PlayoffConfig(
            teams=raw["playoffs"]["teams"],
            weeks=tuple(raw["playoffs"]["weeks"]),
            tie_breaker=raw["playoffs"]["tie_breaker"],
            reseeding=raw["playoffs"]["reseeding"],
            seeding=raw["playoffs"]["seeding"],
        ),
        waiver=WaiverConfig(**raw["waiver"]),
    )


def load_model_config(path: Path) -> ModelConfig:
    raw = _load_yaml(path)
    return ModelConfig(
        recency_weights={int(k): v for k, v in raw["recency_weights"].items()},
        regression_samples=raw["regression_samples"],
        games_active=GamesActiveConfig(**raw["games_active"]),
        overlay=OverlayConfig(**raw["overlay"]),
        uncertainty=UncertaintyConfig(
            method=raw["uncertainty"]["method"],
            n_samples=raw["uncertainty"]["n_samples"],
            percentiles=tuple(raw["uncertainty"]["percentiles"]),
        ),
        team_changer=TeamChangerConfig(**raw["team_changer"]),
        rookie=RookieConfig(draft_round_buckets=tuple(raw["rookie"]["draft_round_buckets"])),
    )


def load_ranking_config(path: Path) -> RankingConfig:
    raw = _load_yaml(path)
    return RankingConfig(**raw)


def load_sources_config(path: Path) -> SourcesConfig:
    raw = _load_yaml(path)
    return SourcesConfig(
        seasons=SeasonsConfig(**raw["seasons"]),
        required=tuple(raw["required"]),
        optional=tuple(raw["optional"]),
        fallback_behavior=FallbackConfig(**raw["fallback_behavior"]),
    )


# ---------------------------------------------------------------------------
# Aggregate loader
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProjectConfig:
    scoring: ScoringConfig
    league: LeagueConfig
    model: ModelConfig
    ranking: RankingConfig
    sources: SourcesConfig
    config_hash: str


def _compute_config_hash(config_dir: Path) -> str:
    """Deterministic SHA-256 over all config files sorted by name."""
    h = hashlib.sha256()
    for p in sorted(config_dir.glob("*.yaml")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def load_project_config(config_dir: str | Path = "configs") -> ProjectConfig:
    config_dir = Path(config_dir)
    if not config_dir.is_dir():
        raise FileNotFoundError(f"Config directory not found: {config_dir}")

    scoring = load_scoring_config(config_dir / "scoring.yaml")
    league = load_league_config(config_dir / "league.yaml")
    model = load_model_config(config_dir / "model.yaml")
    ranking = load_ranking_config(config_dir / "ranking.yaml")
    sources = load_sources_config(config_dir / "sources.yaml")
    config_hash = _compute_config_hash(config_dir)

    return ProjectConfig(
        scoring=scoring,
        league=league,
        model=model,
        ranking=ranking,
        sources=sources,
        config_hash=config_hash,
    )
