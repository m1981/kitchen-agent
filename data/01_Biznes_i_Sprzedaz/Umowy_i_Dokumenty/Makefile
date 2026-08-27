# Konfiguracja żyje wyłącznie w tym katalogu — nie dotyka reszty repo.
VENV  := .venv
PY    := $(VENV)/bin/python
PIP   := $(VENV)/bin/pip
STAMP := $(VENV)/.installed

# Interpreter do zbudowania venv. "auto" bierze pierwszy, który faktycznie
# potrafi utworzyć środowisko — na macOS z Homebrew trafiają się buildy
# z zepsutym ensurepip. Wymuszenie: make PYTHON=python3.12 test
PYTHON ?= auto
KANDYDACI := python3 python3.13 python3.12 python3.11
DANE ?=

.DEFAULT_GOAL := help
.PHONY: help init install test gen clean

help:
	@echo "make test            - uruchamia testy (sam robi init + install)"
	@echo "make gen             - generuje umowę z danych w generator.py"
	@echo "make gen DANE=x.json - generuje umowę z pliku JSON"
	@echo "make init            - tworzy .venv"
	@echo "make install         - instaluje zależności"
	@echo "make clean           - usuwa .venv, cache i wygenerowane dokumenty"

# --- środowisko ------------------------------------------------------------
# test i gen mają init/install jako prerekwizyty, więc świeży klon działa
# od pierwszego `make test`. Znacznik $(STAMP) pilnuje, żeby instalacja nie
# powtarzała się bez potrzeby — odświeży ją dopiero zmiana pyproject.toml.
init: $(PY)

$(PY):
	@set -e; \
	if [ "$(PYTHON)" != "auto" ]; then \
	    echo "venv: $(PYTHON)"; $(PYTHON) -m venv $(VENV); \
	else \
	    for kandydat in $(KANDYDACI); do \
	        command -v $$kandydat >/dev/null 2>&1 || continue; \
	        rm -rf $(VENV); \
	        if $$kandydat -m venv $(VENV) >/dev/null 2>&1; then \
	            echo "venv: $$kandydat ($$($$kandydat --version))"; break; \
	        fi; \
	    done; \
	fi; \
	if [ ! -x $(PY) ]; then \
	    echo "BŁĄD: żaden z interpreterów ($(KANDYDACI)) nie utworzył venv."; \
	    echo "Wskaż działający: make PYTHON=/sciezka/do/python test"; \
	    exit 1; \
	fi

install: $(STAMP)

$(STAMP): pyproject.toml | $(PY)
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet --editable ".[dev]"
	@touch $@

# --- praca -----------------------------------------------------------------
test: install
	$(PY) -m pytest

gen: install
	$(PY) generator.py $(DANE)

clean:
	rm -rf $(VENV) .pytest_cache __pycache__ tests/__pycache__ *.egg-info wygenerowane
