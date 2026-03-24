import argparse
import sys


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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="ffmodel",
        description="Fantasy football projection system — 2026 preseason",
    )
    subparsers = parser.add_subparsers(dest="command", help="Pipeline step to run")

    # ingest
    ingest_parser = subparsers.add_parser("ingest", help="Extract source data to bronze layer")
    _add_as_of_date(ingest_parser)
    _add_config_dir(ingest_parser)

    # transform
    transform_parser = subparsers.add_parser("transform", help="Normalize raw data to silver canonical tables")
    _add_as_of_date(transform_parser)
    _add_config_dir(transform_parser)

    # features
    features_parser = subparsers.add_parser("features", help="Compute gold-layer model-ready features")
    _add_as_of_date(features_parser)
    _add_config_dir(features_parser)

    # project
    project_parser = subparsers.add_parser("project", help="Run position models to produce stat projections")
    _add_as_of_date(project_parser)
    _add_config_dir(project_parser)

    # rank
    rank_parser = subparsers.add_parser("rank", help="Score, rank, and compute VOR from projections")
    _add_as_of_date(rank_parser)
    _add_config_dir(rank_parser)

    # run (full pipeline)
    run_parser = subparsers.add_parser("run", help="Execute full pipeline: ingest through export")
    _add_as_of_date(run_parser)
    _add_config_dir(run_parser)

    # backtest
    backtest_parser = subparsers.add_parser("backtest", help="Rolling-origin historical evaluation")
    backtest_parser.add_argument(
        "--seasons",
        required=True,
        help="Comma-separated holdout seasons (e.g. 2023,2024,2025)",
    )
    _add_config_dir(backtest_parser)

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Dispatch will be implemented in later phases
    print(f"[ffmodel] command={args.command} — not yet implemented")
