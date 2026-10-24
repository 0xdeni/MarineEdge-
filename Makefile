.PHONY: dev test api web demo lint
dev: ## app + API on :8080 with the generated demo fleet (in-memory, stdlib only). First account: server admin password dev-setup-code
	cd backend && API_TOKENS=admin:dev-setup-code:admin python3 -m app.devserver
test:
	cd backend && (pytest -q || python3 -m tests.run)
lint:
	cd backend && ruff check app tests
demo: ## a sample PDF report from the demo fleet (needs Playwright's Chromium)
	cd backend && VVT_PROVIDER=mock VVT_ALLOW_MOCK=1 python3 -m app.cli report 9000013
