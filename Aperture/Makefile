# Params
CXX = g++
PYTHON3 ?= python3
DEBUG_FLAGS = -g -O0 -DDEBUG
RELEASE_FLAGS = -O3 -DNDEBUG
RES_FLAGS ?= $(DEBUG_FLAGS)
CXXFLAGS += -std=c++20 -Wall -MMD -MP $(RES_FLAGS)
LDFLAGS := -lz

# Directories
PROJECT_ROOT := $(CURDIR)
SRC_DIR := $(PROJECT_ROOT)/src
BUILD_DIR := $(PROJECT_ROOT)/build
EXTERNAL_DIR := $(PROJECT_ROOT)/external
SOLVERS_DIR := $(EXTERNAL_DIR)/solvers

CADICAL_DIR := $(SOLVERS_DIR)/cadical
GLUCOSE_DIR := $(SOLVERS_DIR)/glucose
KISSAT_DIR := $(SOLVERS_DIR)/AE_kissat2025_MAB
TOPOR_DIR := $(SOLVERS_DIR)/topor
SOLVER_DIRS := $(CADICAL_DIR) $(GLUCOSE_DIR) $(KISSAT_DIR) $(TOPOR_DIR)

# Files
SRC_FILES := $(shell find $(SRC_DIR) -name "*.cc")
OBJ_FILES := $(patsubst $(SRC_DIR)/%.cc,$(BUILD_DIR)/%.o,$(SRC_FILES))
DEP_FILES := $(OBJ_FILES:.o=.d)
TARGET_NAME := aperture

ifdef STATIC
	CXXFLAGS += -static
	LDFLAGS += -static
	TARGET_NAME := $(TARGET_NAME)_static
endif

TARGET_EXEC := $(BUILD_DIR)/$(TARGET_NAME)

# Solvers Libraries
CADICAL_LIB := $(CADICAL_DIR)/build/libcadical.a
GLUCOSE_LIB := $(GLUCOSE_DIR)/core/libglucose_release.a
KISSAT_LIB := $(KISSAT_DIR)/build/libkissat.a
TOPOR_LIB := $(TOPOR_DIR)/libtopor.a
SOLVER_LIBS := $(CADICAL_LIB) $(TOPOR_LIB) $(GLUCOSE_LIB) $(KISSAT_LIB)

# Compilation
CXXFLAGS += -I$(PROJECT_ROOT) -I$(EXTERNAL_DIR) -I$(SOLVERS_DIR) -I$(CADICAL_DIR)/src -I$(TOPOR_DIR) -I$(GLUCOSE_DIR) -I$(KISSAT_DIR)/src -DNBUILD
$(BUILD_DIR)/%.o: $(SRC_DIR)/%.cc
	@mkdir -p $(dir $@)
	$(CXX) -c $(CXXFLAGS) $< -o $@

# Libraries Compilation
$(CADICAL_LIB):
	@echo "Building CaDiCaL library..."
	cd $(CADICAL_DIR) && ./configure && $(MAKE)
	@echo "CaDiCaL library built successfully"

$(TOPOR_LIB):
	@echo "Building Topor library..."
	cd $(TOPOR_DIR) && $(MAKE) libr
	ar d $@ Main.or 2>/dev/null || true
	@echo "Topor library built successfully"

$(GLUCOSE_LIB):
	@echo "Building Glucose library..."
	cd $(GLUCOSE_DIR)/core && \
	$(MAKE) -f ../mtl/template.mk libr \
	LIB=glucose \
	MROOT=.. \
	DEPDIR="core utils" \
	EXEC=glucose
	@echo "Glucose library built successfully"

$(KISSAT_LIB):
	@echo "Building Kissat library..."
	cd $(KISSAT_DIR) && CC=gcc && (test -f build/makefile || ./configure) && $(MAKE) -C build
	@echo "Kissat library built successfully"

# Linking
$(TARGET_EXEC): $(OBJ_FILES) $(SOLVER_LIBS)
	$(CXX) $^ $(LDFLAGS) -o $@

# Static Library Linking
TARGET_LIBS := $(BUILD_DIR)/libaperture.a
LIB_OBJS := $(filter-out %Main.o %main.o,$(OBJ_FILES))

$(TARGET_LIBS): $(SOLVER_LIBS) $(LIB_OBJS)
	@echo "Building merged static library..."
	$(file > $(BUILD_DIR)/.merge.mri,CREATE $@)
	$(foreach o,$(LIB_OBJS),$(file >> $(BUILD_DIR)/.merge.mri,ADDMOD $(o)))
	$(foreach l,$(SOLVER_LIBS),$(file >> $(BUILD_DIR)/.merge.mri,ADDLIB $(l)))
	$(file >> $(BUILD_DIR)/.merge.mri,SAVE)
	$(file >> $(BUILD_DIR)/.merge.mri,END)
	ar -M < $(BUILD_DIR)/.merge.mri
	@rm -f $(BUILD_DIR)/.merge.mri

# Main Rules

all: $(TARGET_EXEC)

clean:
	rm -rf $(BUILD_DIR)

clean-all: clean
	cd $(CADICAL_DIR)/build && $(MAKE) clean 2>/dev/null || true
	cd $(TOPOR_DIR) && $(MAKE) clean 2>/dev/null || true
	cd $(GLUCOSE_DIR)/core && $(MAKE) -f ../mtl/template.mk clean MROOT=.. DEPDIR="core utils" 2>/dev/null || true
	rm -f $(GLUCOSE_DIR)/core/libglucose*.a 2>/dev/null || true
	cd $(KISSAT_DIR) && $(MAKE) clean 2>/dev/null || true
	rm -rf $(KISSAT_DIR)/build
	rm -rf $(KISSAT_DIR)/build_pic
	rm -rf $(CADICAL_DIR)/build_pic

debug:
	$(MAKE) clean
	$(MAKE) all RES_FLAGS="$(DEBUG_FLAGS)"

dev:
	$(MAKE) all RES_FLAGS="$(RELEASE_FLAGS)"

dev-static:
	$(MAKE) all RES_FLAGS="$(RELEASE_FLAGS)" STATIC=1

release:
	$(MAKE) clean-all
	$(MAKE) all RES_FLAGS="$(RELEASE_FLAGS)"

release-static:
	$(MAKE) clean-all
	$(MAKE) all RES_FLAGS="$(RELEASE_FLAGS)" STATIC=1

lib-static:
	$(MAKE) clean-all
	$(MAKE) $(TARGET_LIBS) RES_FLAGS="$(RELEASE_FLAGS)"

ds: dev-static
rs: release-static
ls: lib-static

# Tests

GTEST_DIR := $(EXTERNAL_DIR)/googletest-main/googletest
GTEST_INCLUDE_DIR := $(GTEST_DIR)/include
GTEST_SRC_DIR := $(GTEST_DIR)/src

TEST_CXXFLAGS := $(CXXFLAGS) -I$(GTEST_DIR) -I$(GTEST_INCLUDE_DIR)
TEST_LDFLAGS := -lpthread
TEST_SRC_DIR := ./tests
TEST_BUILD_DIR := $(BUILD_DIR)/tests
TEST_SRC_FILES := $(shell find $(TEST_SRC_DIR) -name "*.cc")
TEST_OBJS := $(patsubst $(TEST_SRC_DIR)/%.cc,$(TEST_BUILD_DIR)/%.o,$(TEST_SRC_FILES))
TEST_DEPS := $(TEST_OBJS:.o=.d)
GTEST_SRC_FILES := $(GTEST_SRC_DIR)/gtest-all.cc $(GTEST_SRC_DIR)/gtest_main.cc
GTEST_OBJS := $(patsubst $(GTEST_SRC_DIR)/%.cc,$(TEST_BUILD_DIR)/googletest/%.o,$(GTEST_SRC_FILES))
TEST_EXEC := $(BUILD_DIR)/test_suite

$(TEST_BUILD_DIR)/%.o: $(TEST_SRC_DIR)/%.cc
	@mkdir -p $(dir $@)
	$(CXX) -c -I$(SRC_DIR) $(TEST_CXXFLAGS) $< -o $@

$(TEST_BUILD_DIR)/googletest/%.o: $(GTEST_SRC_DIR)/%.cc
	@mkdir -p $(dir $@)
	$(CXX) -c $(TEST_CXXFLAGS) $< -o $@

$(TEST_EXEC): $(TEST_OBJS) $(LIB_OBJS) $(GTEST_OBJS) $(SOLVER_LIBS)
	$(CXX) $(TEST_OBJS) $(LIB_OBJS) $(GTEST_OBJS) $(SOLVER_LIBS) $(LDFLAGS) $(TEST_LDFLAGS) -o $@

build-tests: $(TEST_EXEC)

run-tests: $(TEST_EXEC)
	$(TEST_EXEC)

# Python

CADICAL_PIC_LIB := $(CADICAL_DIR)/build_pic/libcadical.a
CADICAL_BUILD_TARGET ?=
GLUCOSE_PIC_LIB := $(GLUCOSE_DIR)/core/libglucose_pic.a
KISSAT_PIC_LIB  := $(KISSAT_DIR)/build_pic/libkissat.a
TOPOR_PIC_LIB   := $(TOPOR_DIR)/libtopor_pic.a
SOLVER_PIC_LIBS := $(CADICAL_PIC_LIB) $(TOPOR_PIC_LIB) $(GLUCOSE_PIC_LIB) $(KISSAT_PIC_LIB)

PIC_BUILD_DIR  := $(BUILD_DIR)/pic
PIC_OBJ_FILES  := $(patsubst $(SRC_DIR)/%.cc,$(PIC_BUILD_DIR)/%.o,$(SRC_FILES))
LIB_PIC_OBJS   := $(filter-out %Main.o %main.o,$(PIC_OBJ_FILES))
PIC_DEP_FILES  := $(LIB_PIC_OBJS:.o=.d)
TARGET_PIC_LIB := $(BUILD_DIR)/libaperture_pic.a

$(PIC_BUILD_DIR)/%.o: $(SRC_DIR)/%.cc
	@mkdir -p $(dir $@)
	$(CXX) -c $(CXXFLAGS) -fPIC $< -o $@

$(CADICAL_PIC_LIB):
	@echo "Building CaDiCaL PIC library..."
	rm -rf $(CADICAL_DIR)/build_pic
	mkdir $(CADICAL_DIR)/build_pic
	# CaDiCaL's configure appends flags to inherited CFLAGS without a separator.
	# Do not pass Hermax's C-only flags into this C++ sub-build.
	cd $(CADICAL_DIR)/build_pic && CFLAGS= ../configure -fPIC && $(MAKE) $(CADICAL_BUILD_TARGET)
	@echo "CaDiCaL PIC library built successfully"

$(KISSAT_PIC_LIB):
	@echo "Building Kissat PIC library..."
	mkdir -p $(KISSAT_DIR)/build_pic
	cd $(KISSAT_DIR)/build_pic && ../configure -fPIC && $(MAKE)
	@echo "Kissat PIC library built successfully"

$(GLUCOSE_PIC_LIB):
	@echo "Building Glucose PIC library..."
	cd $(GLUCOSE_DIR)/core && \
	$(MAKE) -f ../mtl/template.mk librh \
	LIB=glucose \
	MROOT=.. \
	DEPDIR="core utils" \
	EXEC=glucose
	find $(GLUCOSE_DIR) -name "*.oh" ! -name "Main.oh" | sort | xargs ar rcs $@
	@echo "Glucose PIC library built successfully"

$(TOPOR_PIC_LIB):
	@echo "Building Topor PIC library..."
	# Topor is C++; do not let Hermax's CFLAGS override its C++20 defaults.
	cd $(TOPOR_DIR) && $(MAKE) librh \
		CFLAGS="$(CXXFLAGS) -DSKIP_ZLIB -Wall -Wno-parentheses -std=c++20"
	find $(TOPOR_DIR) -maxdepth 1 -name "*.oh" ! -name "Main.oh" | sort | xargs ar rcs $@
	@echo "Topor PIC library built successfully"

$(TARGET_PIC_LIB): $(SOLVER_PIC_LIBS) $(LIB_PIC_OBJS)
	@echo "Building merged PIC static library..."
	$(file > $(BUILD_DIR)/.merge_pic.mri,CREATE $@)
	$(foreach o,$(LIB_PIC_OBJS),$(file >> $(BUILD_DIR)/.merge_pic.mri,ADDMOD $(o)))
	$(foreach l,$(SOLVER_PIC_LIBS),$(file >> $(BUILD_DIR)/.merge_pic.mri,ADDLIB $(l)))
	$(file >> $(BUILD_DIR)/.merge_pic.mri,SAVE)
	$(file >> $(BUILD_DIR)/.merge_pic.mri,END)
	ar -M < $(BUILD_DIR)/.merge_pic.mri
	@rm -f $(BUILD_DIR)/.merge_pic.mri

lib-pic:
	$(MAKE) $(TARGET_PIC_LIB) RES_FLAGS="$(RELEASE_FLAGS)"

lp: lib-pic

# Python bindings (nanobind)
PYTHON_INCLUDES   := $(shell $(PYTHON3) -c "import sysconfig; print(sysconfig.get_path('include'))")
NANOBIND_DIR      := $(shell $(PYTHON3) -c "import nanobind, os; print(os.path.dirname(nanobind.include_dir()))" 2>/dev/null || true)
ifeq ($(filter lib-python lpy,$(MAKECMDGOALS)),)
	ifeq ($(strip $(NANOBIND_DIR)),)
		NANOBIND_INCLUDES :=
	else
		NANOBIND_INCLUDES := $(NANOBIND_DIR)/include
	endif
else
	ifeq ($(strip $(NANOBIND_DIR)),)
	$(error nanobind not found. Install it with: pip install nanobind)
	endif
	NANOBIND_INCLUDES := $(NANOBIND_DIR)/include
endif

PY_MODULE_NAME	  := _aperture
PY_SRC_DIR  := $(PROJECT_ROOT)/aperture/_core
PY_BUILD_DIR := $(PIC_BUILD_DIR)/python
PY_SRC_FILES := $(shell find $(PY_SRC_DIR) -name "*.cc")
PY_OBJ      := $(patsubst $(PY_SRC_DIR)/%.cc,$(PY_BUILD_DIR)/%.o,$(PY_SRC_FILES))
PY_DEP_FILES := $(PY_OBJ:.o=.d)
NB_OBJ      := $(PY_BUILD_DIR)/nb_combined.o
PY_MODULE   := $(PROJECT_ROOT)/aperture/$(PY_MODULE_NAME).so

PY_CXXFLAGS := $(CXXFLAGS) -fPIC -I$(PYTHON_INCLUDES) -I$(NANOBIND_INCLUDES) -I$(NANOBIND_DIR)/ext/robin_map/include

$(PY_BUILD_DIR)/%.o: $(PY_SRC_DIR)/%.cc
	@mkdir -p $(dir $@)
	$(CXX) -c $(PY_CXXFLAGS) $< -o $@

$(NB_OBJ): $(NANOBIND_DIR)/src/nb_combined.cpp
	@mkdir -p $(dir $@)
	$(CXX) -c $(PY_CXXFLAGS) $< -o $@

$(PY_MODULE): $(PY_OBJ) $(NB_OBJ) $(TARGET_PIC_LIB)
	$(CXX) -shared -fPIC $^ $(LDFLAGS) -o $@

lib-python:
	$(MAKE) $(PY_MODULE) RES_FLAGS="$(RELEASE_FLAGS)"

lpy: lib-python

.DEFAULT_GOAL := rs

.PHONY: all clean clean-all debug release release-static rs dev dev-static ds lib-static ls build-tests run-tests lib-pic lp lib-python lpy

-include $(DEP_FILES) $(TEST_DEPS) $(PY_DEP_FILES) $(PIC_DEP_FILES)
