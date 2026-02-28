APP=src.llm_thalamus
PYTHON=python

DATA_DIR=var/llm-thalamus-dev
STATE_DIR=$(DATA_DIR)/state
DB_DIR=$(DATA_DIR)/data

.PHONY: help run test clean reset-state reset-db

help:
	@echo "Available targets:"
	@echo "  make run           - Run the application"
	@echo "  make test          - Run runtime probe test"
	@echo "  make reset-state   - Remove world_state.json"
	@echo "  make reset-db      - Remove sqlite databases"
	@echo "  make clean         - Clean logs and caches"

run:
	$(PYTHON) -m $(APP)

test:
	$(PYTHON) -m src.tests.langgraph_test
	@echo "Additional probes available under src/tests/"

reset-state:
	rm -f $(STATE_DIR)/world_state.json
	@echo "World state reset."

reset-db:
	rm -f $(DB_DIR)/memory.sqlite
	rm -f $(DB_DIR)/episodes.sqlite
	@echo "Databases removed."

clean:
	rm -f thinking-manual-*.log
	find . -name "__pycache__" -type d -exec rm -rf {} +
	@echo "Clean complete."
