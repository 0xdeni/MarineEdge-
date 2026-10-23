.PHONY: dev test api web demo lint
dev: ## run API (mock provider, in-memory cache) and static web on :8000 / :8080
	cd backend && VVT_PROVIDER=mock uvicorn app.main:app --reload --port 8000 &
	cd frontend/public && python3 -m http.server 8080
test:
	cd backend && (pytest -q || python3 -m tests.run)
lint:
	cd backend && ruff check app tests
demo: ## generate a sample PDF report with the mock provider
	cd backend && python3 -c "from app.service import Service; from app.reports.render import render_html, render_pdf; s=Service(); a=s.analysis(9000036); print(render_pdf(render_html(a), 9000036))"
