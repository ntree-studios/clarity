IMAGE ?= clarity
ARGS ?= check -
JSCPD_VERSION ?= 5.4.3

.PHONY: build test test-corpus lint run docs

build:
	docker build -t $(IMAGE) .

test:
	docker build --target dev -t $(IMAGE)-dev .
	docker run --rm $(IMAGE)-dev sh -c "pytest && clarity test"

# make test-corpus CORPUS=~/writing/published [AGAINST=~/writing/slop]
test-corpus:
	@test -n "$(CORPUS)" || (echo "set CORPUS=<path>"; exit 2)
	docker build --target dev -t $(IMAGE)-dev .
	docker run --rm -v "$(CORPUS):/corpus:ro" $(if $(AGAINST),-v "$(AGAINST):/against:ro") \
		$(IMAGE)-dev clarity test --corpus /corpus $(if $(AGAINST),--against /against)

lint:
	docker build --target dev -t $(IMAGE)-dev .
	docker run --rm $(IMAGE)-dev sh -c "ruff check . && mypy src"
	npx --yes jscpd@$(JSCPD_VERSION) --config .jscpd.json

run:
	docker run -i --rm $(IMAGE) $(ARGS)

# Rewrite the README regions that are rendered from the schema. The test suite fails if they are stale.
docs:
	docker build --target dev -t $(IMAGE)-dev .
	docker run --rm -v "$(PWD)":/app -w /app $(IMAGE)-dev clarity surface --sync README.md
