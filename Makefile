.PHONY: up down restart logs ps check clean

up:
	docker compose up --build -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

check:
	./scripts/check.sh

clean:
	docker compose down -v
