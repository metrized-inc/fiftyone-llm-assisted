# To run this makefile you will need make and cygwin install on your PC


# COLORS
BLUE = \e[1;36m
GREEN = \e[1;32m
GRAY = \e[38;5;247m
RESET = \e[0m

# VARIABLES 
CYGWIN_PATH := C:\cygwin64 # Modify this to the proper cygwin path
SHELL := $(CYGWIN_PATH)\bin\bash
FIND := $(CYGWIN_PATH)\bin\find
SRC := src
TESTS := tests
VENV := venv
PYTHON := ./$(VENV)/Scripts/python.exe


.PHONY: help
help: 
	@echo -e 'Metrized Autodocs Makefile$(GRAY)'
	@echo 'Usage:'
	@echo '	make install	Install dependencies and src into a venv.'
	@echo '	make format	Format the source code in python.'
	@echo '	make test	Run all the tests for the project.'
	@echo -e '	make clean	Remove all python-generated files.$(RESET)'

.PHONY: clean
clean:
	@echo 'Cleaning up...'
	@$(FIND) $(SRC) -regex '^.*\(__pycache__\|\.py[co]\)$ ' -delete
	@$(FIND) $(TESTS) -regex '^.*\(__pycache__\|\.py[co]\)$ ' -delete
	@rm -rf $(SRC)/*.egg-info .pytest_cache $(VENV)
	@echo 'Done!'

.PHONY: install
install: $(VENV)/.install-stamp
	@echo -e '$(RESET)Finished install!'
	@echo -e 'Activate venv with: $(BLUE)source ./$(VENV)/bin/activate$(RESET)'


.PHONY: format
format: $(PYTHON)
	@echo 'Formatting the $(SRC) directory...'
	@$(PYTHON) -m black $(SRC)

.PHONY: test
test: $(PYTHON)
	@echo 'Running tests...'
	@$(PYTHON) -m pytest $(TESTS)

$(PYTHON):
	@echo 'Creating virtual environment...'
	@python -m venv $(VENV)
	@$(PYTHON) -m pip install -q --upgrade pip black pytest

$(VENV)/.install-stamp: $(PYTHON) pyproject.toml requirements.txt
	@echo -e 'Installing the local package and dependencies...$(GRAY)'
	@$(PYTHON) -m pip install -e .
	@touch $@