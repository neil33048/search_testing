# Meridian Commerce Platform - Makefile
# Run `make help` for available commands

.PHONY: help install install-dev setup db-setup db-migrate db-seed \
        dev run test test-unit test-integration test-all lint format \
        typecheck clean build docker-build docker-up docker-down \
        deploy-staging deploy-prod forge-run beacon-test pulse-refresh \
        catalyst-train docs

# Default goal
.DEFAULT_GOAL := help

# Variables
PYTHON := python3
PIP := pip3
DOCKER_COMPOSE := docker compose
PROJECT_NAME := meridian-commerce

# Colors for terminal output
CYAN := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RESET := \033[0m

help: ## Show this help message
	@echo "$(CYAN)Meridian Commerce Platform$(RESET)"
	@echo "$(YELLOW)Available commands:$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'

# =============================================================================
# Installation & Setup
# =============================================================================

install: ## Install production dependencies
	$(PIP) install -r requirements.txt

install-dev: ## Install development dependencies
	$(PIP) install -r requirements-dev.txt
	pre-commit install

setup: install-dev db-setup ## Full development environment setup
	@echo "$(GREEN)Development environment ready!$(RESET)"

# =============================================================================
# Database Commands
# =============================================================================

db-setup: ## Create and initialize local database
	@echo "$(CYAN)Setting up database...$(RESET)"
	./scripts/setup_db.sh

db-migrate: ## Run database migrations
	@echo "$(CYAN)Running migrations...$(RESET)"
	alembic upgrade head

db-migrate-create: ## Create a new migration (usage: make db-migrate-create MSG="description")
	alembic revision --autogenerate -m "$(MSG)"

db-seed: ## Seed database with sample data
	@echo "$(CYAN)Seeding database...$(RESET)"
	$(PYTHON) scripts/seed_data.py

db-reset: ## Reset database (drop and recreate)
	@echo "$(YELLOW)Warning: This will delete all data!$(RESET)"
	dropdb --if-exists meridian_dev
	createdb meridian_dev
	$(MAKE) db-migrate db-seed

# =============================================================================
# Development
# =============================================================================

dev: ## Run development server with auto-reload
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

run: ## Run production server
	uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4

shell: ## Open Python shell with app context
	$(PYTHON) -c "from src.core.database import engine; from src.models import *" -i

# =============================================================================
# Testing
# =============================================================================

test: test-unit ## Run default tests (unit tests)

test-unit: ## Run unit tests
	pytest tests/unit -v --tb=short

test-integration: ## Run integration tests
	pytest tests/integration -v --tb=short -m integration

test-all: ## Run all tests with coverage
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing

test-fast: ## Run tests without slow markers
	pytest tests/unit -v -m "not slow" --tb=short

test-catalyst: ## Run Catalyst recommendation engine tests
	pytest tests/unit/test_catalyst tests/integration -v -m catalyst

test-forge: ## Run Forge pipeline tests
	pytest tests/unit/test_forge tests/integration -v -m forge

test-watch: ## Run tests in watch mode
	ptw -- --tb=short

# =============================================================================
# Code Quality
# =============================================================================

lint: ## Run linter (ruff)
	ruff check src tests

lint-fix: ## Run linter with auto-fix
	ruff check src tests --fix

format: ## Format code (ruff)
	ruff format src tests

format-check: ## Check code formatting
	ruff format src tests --check

typecheck: ## Run type checker (mypy)
	mypy src

quality: lint typecheck ## Run all code quality checks

# =============================================================================
# Docker
# =============================================================================

docker-build: ## Build Docker images
	$(DOCKER_COMPOSE) build

docker-up: ## Start all services
	$(DOCKER_COMPOSE) up -d

docker-down: ## Stop all services
	$(DOCKER_COMPOSE) down

docker-logs: ## Show service logs
	$(DOCKER_COMPOSE) logs -f

docker-shell: ## Open shell in app container
	$(DOCKER_COMPOSE) exec app /bin/bash

docker-clean: ## Remove all containers and volumes
	$(DOCKER_COMPOSE) down -v --remove-orphans

# =============================================================================
# Data Pipelines (Forge)
# =============================================================================

forge-run: ## Run Forge ETL pipeline
	$(PYTHON) -m src.forge.cli run --all

forge-validate: ## Validate pipeline configurations
	$(PYTHON) -m src.forge.cli validate

dbt-run: ## Run dbt models
	cd pipelines/dbt && dbt run

dbt-test: ## Test dbt models
	cd pipelines/dbt && dbt test

dbt-docs: ## Generate dbt documentation
	cd pipelines/dbt && dbt docs generate && dbt docs serve

airflow-init: ## Initialize Airflow database
	airflow db init

airflow-webserver: ## Start Airflow webserver
	airflow webserver --port 8080

airflow-scheduler: ## Start Airflow scheduler
	airflow scheduler

# =============================================================================
# Beacon (Event Collection)
# =============================================================================

beacon-test: ## Test Beacon event ingestion
	$(PYTHON) -m src.beacon.cli test-ingestion

beacon-validate: ## Validate Beacon event schemas
	$(PYTHON) -m src.beacon.cli validate-schemas

# =============================================================================
# Pulse (Analytics)
# =============================================================================

pulse-refresh: ## Refresh Pulse materialized views
	$(PYTHON) -m src.pulse.cli refresh-views

pulse-cache-warm: ## Warm Pulse dashboard cache
	$(PYTHON) -m src.pulse.cli warm-cache

# =============================================================================
# Catalyst (Recommendations)
# =============================================================================

catalyst-train: ## Train Catalyst recommendation models
	$(PYTHON) -m src.catalyst.cli train --model=collaborative

catalyst-evaluate: ## Evaluate model performance
	$(PYTHON) -m src.catalyst.cli evaluate

catalyst-deploy: ## Deploy trained model to serving
	$(PYTHON) -m src.catalyst.cli deploy --version=$(VERSION)

# =============================================================================
# Documentation
# =============================================================================

docs: ## Build documentation
	mkdocs build

docs-serve: ## Serve documentation locally
	mkdocs serve

# =============================================================================
# Deployment
# =============================================================================

deploy-staging: ## Deploy to staging environment
	@echo "$(CYAN)Deploying to staging...$(RESET)"
	./scripts/deploy.sh staging

deploy-prod: ## Deploy to production (requires approval)
	@echo "$(YELLOW)Deploying to production...$(RESET)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	./scripts/deploy.sh production

# =============================================================================
# Cleanup
# =============================================================================

clean: ## Clean build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

clean-all: clean docker-clean ## Clean everything including Docker
	@echo "$(GREEN)All cleaned up!$(RESET)"

# =============================================================================
# Utilities
# =============================================================================

generate-secret: ## Generate a secure secret key
	@$(PYTHON) -c "import secrets; print(secrets.token_urlsafe(32))"

check-deps: ## Check for outdated dependencies
	pip list --outdated

update-deps: ## Update dependencies
	pip-compile requirements.in -o requirements.txt
	pip-compile requirements-dev.in -o requirements-dev.txt

security-scan: ## Run security vulnerability scan
	safety check -r requirements.txt
	bandit -r src/

loc: ## Count lines of code
	@find src -name "*.py" | xargs wc -l | tail -1
	@echo "$(CYAN)(Python source files only)$(RESET)"
