# Colors for help system
BLUE := \033[36m
YELLOW := \033[33m
GREEN := \033[32m
RESET := \033[0m

# Paths
FRONTEND_DIR := frontend

.DEFAULT_GOAL := help

##@ General
.PHONY: help
help: ## Display this help
	@awk 'BEGIN {FS = ":.*##"; printf "\n$(BLUE)Usage:$(RESET)\n  make $(YELLOW)<target>$(RESET)\n"} \
		/^[a-zA-Z0-9_-]+:.*?##/ { printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2 } \
		/^##@/ { printf "\n$(GREEN)%s$(RESET)\n", substr($$0, 5) }' $(MAKEFILE_LIST)

##@ Development
.PHONY: server
server: ## Start the backend server (uvicorn with hot reload)
	@echo "$(GREEN)Starting backend server...$(RESET)"
	uv run uvicorn src.main:app --reload

.PHONY: frontend
frontend: ## Start the frontend dev server (pnpm)
	@echo "$(GREEN)Starting frontend dev server...$(RESET)"
	cd $(FRONTEND_DIR) && pnpm run dev

.PHONY: dev
dev: ## Start both server and frontend in parallel
	@echo "$(GREEN)Starting server and frontend...$(RESET)"
	@make -j2 server frontend

##@ Testing
.PHONY: ls
ls: ## List meaningful project files (backend + frontend sources, prompts, docs)
	lsproj

.PHONY: test-cov
test-cov: ## Run UNIT tests with strict coverage (Fail under 80%, excludes UI and integration tests)
	@echo "$(GREEN)Running Unit Tests with Coverage Check...$(RESET)"
	uv run pytest -m "not integration" --cov=src  --cov-report=term-missing

