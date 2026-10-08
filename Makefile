# Development tasks. Everything runs on the standard library alone.
.PHONY: help test scan check version release-check clean

help:
	@echo "make test           run the test suite"
	@echo "make scan           scan the repository for secrets and third-party material"
	@echo "make check          test, then scan -- run this before tagging"
	@echo "make version        show the tool and compatibility table"
	@echo "make release-check  verification required before tagging a release"
	@echo "make clean          remove Python build and cache artifacts"

test:
	python3 -m unittest discover -s tests -t . -v

scan:
	./zh-patch scan .

check:
	./scripts/check.sh

version:
	./zh-patch version

release-check: check
	@echo
	@echo "Checklist before tagging:"
	@echo "  [ ] CHANGELOG has a dated section for this version"
	@echo "  [ ] NOTICE and LICENSE still scope the licence to original work only"
	@echo "  [ ] docs/COMPATIBILITY.md matches SUPPORTED_VERSIONS in compat.py"
	@echo "  [ ] README states the verified environment and does not overclaim"
	@echo "  [ ] no language resource, application binary or extracted catalog is staged"
	@echo "  [ ] git status shows only files you intend to publish"

clean:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache
	find . -name '*.py[cod]' -delete
