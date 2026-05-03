.PHONY: help bootstrap dev-up dev-down register-admin logs status clean bulk-map

help:  ## Show this help
	@awk 'BEGIN{FS=":.*##"; printf "Cobweb dev commands:\n\n"} /^[a-zA-Z_-]+:.*##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

bootstrap:  ## First-time setup: env files, docker, deps, migrations
	./scripts/bootstrap.sh

dev-up:  ## Start API, web, nuclei-runner, zap-runner (logs in /tmp/cobweb-*.log)
	./scripts/dev-up.sh

dev-down:  ## Stop the four host processes (docker stack stays up)
	./scripts/dev-down.sh

register-admin:  ## Create first admin + organization (interactive)
	./scripts/register-admin.sh

logs:  ## Tail all dev logs
	tail -f /tmp/cobweb-*.log

status:  ## Show running pids + docker compose state
	@echo "── docker compose ──"
	@docker compose ps
	@echo
	@echo "── host processes ──"
	@for f in /tmp/cobweb-*.pid; do \
	  [ -f "$$f" ] || continue; \
	  name=$$(basename $$f .pid | sed 's/^cobweb-//'); \
	  pid=$$(cat $$f); \
	  if kill -0 $$pid 2>/dev/null; then \
	    printf "  %-20s pid %-7s [running]\n" "$$name" "$$pid"; \
	  else \
	    printf "  %-20s pid %-7s [\033[31mdead\033[0m]\n" "$$name" "$$pid"; \
	  fi; \
	done

clean:  ## Stop everything (host + docker) — keeps volumes
	-./scripts/dev-down.sh
	docker compose down

bulk-map:  ## Classify finding templates → OWASP/PCI/ISO via LLM (one-shot)
	cd apps/api && uv run python -m cobweb.scripts.bulk_compliance_map $(ARGS)
