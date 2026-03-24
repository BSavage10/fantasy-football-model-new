.PHONY: install test run backtest clean

install:
	uv sync

test:
	uv run pytest tests/ -v

run:
	uv run python -m ffmodel run --as-of-date $(AS_OF_DATE)

backtest:
	uv run python -m ffmodel backtest --seasons $(SEASONS)

clean:
	rm -rf data/raw/* data/silver/* data/gold/* outputs/*
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
