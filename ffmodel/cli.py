import argparse
import logging
import sys

from ffmodel.config import load_project_config


def _add_as_of_date(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--as-of-date",
        required=True,
        help="Data freeze date (YYYY-MM-DD). Only information available on or before this date is used.",
    )


def _add_config_dir(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config-dir",
        default="configs",
        help="Path to configuration directory (default: configs)",
    )


def _add_data_dir(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Path to data directory (default: data)",
    )


def _cmd_ingest(args: argparse.Namespace) -> None:
    from ffmodel.ingest.snapshot import run_ingest

    config = load_project_config(args.config_dir)
    out_dir = run_ingest(config.sources, args.as_of_date, data_dir=args.data_dir)
    print(f"[ffmodel] ingest complete → {out_dir}")


def _cmd_features(args: argparse.Namespace) -> None:
    from pathlib import Path

    from ffmodel.features.availability import write_availability_features
    from ffmodel.features.efficiency import write_player_efficiency_features
    from ffmodel.features.manual_factors import write_manual_factor_features
    from ffmodel.features.player_role import write_player_role_features
    from ffmodel.features.team_context import write_team_context_features

    config = load_project_config(args.config_dir)
    data_dir = Path(args.data_dir)
    silver_dir = data_dir / "silver" / args.as_of_date
    gold_dir = data_dir / "gold" / args.as_of_date

    if not silver_dir.exists():
        print(f"[ffmodel] Silver data not found at {silver_dir} — run transform first", file=sys.stderr)
        sys.exit(1)

    target_season = config.sources.seasons.target
    recency_weights = config.model.recency_weights

    write_team_context_features(silver_dir, gold_dir, target_season, recency_weights)

    team_changer_cfg = {
        "player_history_weight": config.model.team_changer.player_history_weight,
        "team_prior_weight": config.model.team_changer.team_prior_weight,
    }
    write_player_role_features(
        silver_dir, gold_dir, target_season, recency_weights, team_changer_cfg,
    )

    write_player_efficiency_features(
        silver_dir, gold_dir, target_season, recency_weights,
        config.model.regression_samples,
    )

    games_active_cfg = {
        "default_max": config.model.games_active.default_max,
        "shrinkage": config.model.games_active.shrinkage,
        "position_prior": config.model.games_active.position_prior,
        "low_sample_threshold": config.model.games_active.low_sample_threshold,
    }
    write_availability_features(
        silver_dir, gold_dir, target_season, recency_weights, games_active_cfg,
    )

    manual_dir = Path("manual")
    write_manual_factor_features(manual_dir, gold_dir, args.as_of_date)

    print(f"[ffmodel] features complete → {gold_dir}")


def _cmd_transform(args: argparse.Namespace) -> None:
    from pathlib import Path

    from ffmodel.transform.player_dim import write_player_dim
    from ffmodel.transform.player_week import write_player_week_fact
    from ffmodel.transform.schedule import write_schedule_fact
    from ffmodel.transform.team_dim import write_team_dim
    from ffmodel.transform.team_week import write_team_week_fact

    config = load_project_config(args.config_dir)
    data_dir = Path(args.data_dir)
    raw_dir = data_dir / "raw" / args.as_of_date
    silver_dir = data_dir / "silver" / args.as_of_date

    if not raw_dir.exists():
        print(f"[ffmodel] Raw data not found at {raw_dir} — run ingest first", file=sys.stderr)
        sys.exit(1)

    seasons = list(range(config.sources.seasons.min, config.sources.seasons.max + 1))

    write_player_dim(raw_dir, silver_dir)
    write_team_dim(raw_dir, silver_dir, seasons)
    write_schedule_fact(raw_dir, silver_dir)
    write_player_week_fact(raw_dir, silver_dir)
    write_team_week_fact(raw_dir, silver_dir)

    print(f"[ffmodel] transform complete → {silver_dir}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="ffmodel",
        description="Fantasy football projection system — 2026 preseason",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    subparsers = parser.add_subparsers(dest="command", help="Pipeline step to run")

    # ingest
    ingest_parser = subparsers.add_parser("ingest", help="Extract source data to bronze layer")
    _add_as_of_date(ingest_parser)
    _add_config_dir(ingest_parser)
    _add_data_dir(ingest_parser)

    # transform
    transform_parser = subparsers.add_parser("transform", help="Normalize raw data to silver canonical tables")
    _add_as_of_date(transform_parser)
    _add_config_dir(transform_parser)
    _add_data_dir(transform_parser)

    # features
    features_parser = subparsers.add_parser("features", help="Compute gold-layer model-ready features")
    _add_as_of_date(features_parser)
    _add_config_dir(features_parser)
    _add_data_dir(features_parser)

    # project
    project_parser = subparsers.add_parser("project", help="Run position models to produce stat projections")
    _add_as_of_date(project_parser)
    _add_config_dir(project_parser)
    _add_data_dir(project_parser)

    # rank
    rank_parser = subparsers.add_parser("rank", help="Score, rank, and compute VOR from projections")
    _add_as_of_date(rank_parser)
    _add_config_dir(rank_parser)
    _add_data_dir(rank_parser)

    # run (full pipeline)
    run_parser = subparsers.add_parser("run", help="Execute full pipeline: ingest through export")
    _add_as_of_date(run_parser)
    _add_config_dir(run_parser)
    _add_data_dir(run_parser)

    # backtest
    backtest_parser = subparsers.add_parser("backtest", help="Rolling-origin historical evaluation")
    backtest_parser.add_argument(
        "--seasons",
        required=True,
        help="Comma-separated holdout seasons (e.g. 2023,2024,2025)",
    )
    _add_config_dir(backtest_parser)
    _add_data_dir(backtest_parser)

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Dispatch
    dispatch = {
        "ingest": _cmd_ingest,
        "transform": _cmd_transform,
        "features": _cmd_features,
    }

    handler = dispatch.get(args.command)
    if handler is not None:
        handler(args)
    else:
        print(f"[ffmodel] command={args.command} — not yet implemented")
