IMAGE ?= clarity
ARGS ?= check -
JSCPD_VERSION ?= 5.4.3

.PHONY: build test lint run

build:
	docker build -t $(IMAGE) .

test:
	docker build --target dev -t $(IMAGE)-dev .
	docker run --rm $(IMAGE)-dev pytest

lint:
	docker build --target dev -t $(IMAGE)-dev .
	docker run --rm $(IMAGE)-dev sh -c "ruff check . && mypy src"
	npx --yes jscpd@$(JSCPD_VERSION) --config .jscpd.json

run:
	docker run -i --rm $(IMAGE) $(ARGS)
