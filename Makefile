SHELL := /bin/bash

# Default CPLEX install (override if needed)
CPLEX_STUDIO ?= /opt/ibm/ILOG/CPLEX_Studio2212
CPLEX_INC_DIR ?= $(CPLEX_STUDIO)/cplex/include
CPLEX_LIB_DIR ?= $(CPLEX_STUDIO)/cplex/lib/x86-64_linux/static_pic

UV ?= uv
PYTHON ?= $(UV) run --active python
WHEEL_OUT ?= wheelhouse
HERMAX_CIBW_TEST_PROFILE ?= full
HERMAX_CIBW_ALLOW_TEST_FAILURE ?= 1
HERMAX_CIBW_COMPLIANCE_TIMEOUT ?= 180

CIBW_ENGINE := podman; create_args: --volume $(CPLEX_STUDIO):$(CPLEX_STUDIO):ro
CIBW_ENV_LINUX_BASE := CPLEX_INC_DIR=$(CPLEX_INC_DIR) CPLEX_LIB_DIR=$(CPLEX_LIB_DIR) HERMAX_ENABLE_MAXHS=on HERMAX_ENABLE_IMAXHS=on SKIP_MAXHS=0 SKIP_IMAXHS=0 HERMAX_CIBW_TEST_PROFILE=$(HERMAX_CIBW_TEST_PROFILE) HERMAX_CIBW_ALLOW_TEST_FAILURE=$(HERMAX_CIBW_ALLOW_TEST_FAILURE) HERMAX_CIBW_COMPLIANCE_TIMEOUT=$(HERMAX_CIBW_COMPLIANCE_TIMEOUT)
CIBW_ENV_LINUX_ONLY_MAXHS_IMAXHS := $(CIBW_ENV_LINUX_BASE) HERMAX_SOLVER_INCLUDE=hermax.core.maxhs_py,hermax.core.imaxhs_py
CIBW_TEST_IMPORT := python -c "import hermax.core.maxhs_py as m, hermax.core.imaxhs_py as i; print(m.__name__, i.__name__)"

.PHONY: check-cplex \
	cibw-maxhs-imaxhs cibw-maxhs-imaxhs-cp314 \
	cibw-full-cplex cibw-full-cplex-cp314

check-cplex:
	@test -f "$(CPLEX_INC_DIR)/ilcplex/cplex.h" || (echo "Missing CPLEX header: $(CPLEX_INC_DIR)/ilcplex/cplex.h" && exit 1)
	@ls "$(CPLEX_LIB_DIR)"/libcplex* >/dev/null 2>&1 || (echo "Missing CPLEX library under: $(CPLEX_LIB_DIR)" && exit 1)
	@echo "CPLEX include: $(CPLEX_INC_DIR)"
	@echo "CPLEX lib    : $(CPLEX_LIB_DIR)"

# Full matrix from pyproject.toml, but only MaxHS/iMaxHS extensions enabled
cibw-maxhs-imaxhs: check-cplex
	CIBW_CONTAINER_ENGINE='$(CIBW_ENGINE)' \
	CIBW_ENVIRONMENT_LINUX='$(CIBW_ENV_LINUX_ONLY_MAXHS_IMAXHS)' \
	CIBW_TEST_COMMAND='$(CIBW_TEST_IMPORT)' \
	$(PYTHON) -m cibuildwheel --output-dir $(WHEEL_OUT)

# Fast path: single wheel target
cibw-maxhs-imaxhs-cp314: check-cplex
	CIBW_BUILD='cp314-manylinux_x86_64' \
	CIBW_CONTAINER_ENGINE='$(CIBW_ENGINE)' \
	CIBW_ENVIRONMENT_LINUX='$(CIBW_ENV_LINUX_ONLY_MAXHS_IMAXHS)' \
	CIBW_TEST_COMMAND='$(CIBW_TEST_IMPORT)' \
	$(PYTHON) -m cibuildwheel --output-dir $(WHEEL_OUT)

# Full matrix from pyproject.toml with CPLEX + MaxHS/iMaxHS enabled, compile everything
cibw-full-cplex: check-cplex
	CIBW_CONTAINER_ENGINE='$(CIBW_ENGINE)' \
	CIBW_ENVIRONMENT_LINUX='$(CIBW_ENV_LINUX_BASE)' \
	$(PYTHON) -m cibuildwheel --output-dir $(WHEEL_OUT)

# Fast path: CPython 3.14, CPLEX + MaxHS/iMaxHS enabled, compile everything
cibw-full-cplex-cp314: check-cplex
	CIBW_BUILD='cp314-manylinux_x86_64' \
	CIBW_CONTAINER_ENGINE='$(CIBW_ENGINE)' \
	CIBW_ENVIRONMENT_LINUX='$(CIBW_ENV_LINUX_BASE)' \
	$(PYTHON) -m cibuildwheel --output-dir $(WHEEL_OUT)
