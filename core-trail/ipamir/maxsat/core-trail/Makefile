SIG=core-trail
TARGET=libipamir$(SIG).a

NATIVE_CORETRAIL=./
JEMALLOC_ROOT ?= $(abspath ./third_party/jemalloc)
JEMALLOC_LIB ?= $(JEMALLOC_ROOT)/lib/libjemalloc.a
LIBS_FILE := LIBS

CXX?=g++
AR?=ar
ARFLAGS?=rcs
BASE_CXXFLAGS=-O3 -DNDEBUG -std=c++17 -fvisibility=hidden -ffunction-sections -fdata-sections
PERF_CXXFLAGS=-fno-semantic-interposition -fomit-frame-pointer -ffp-contract=fast
CXXFLAGS?=$(BASE_CXXFLAGS) $(PERF_CXXFLAGS)
CPPFLAGS+=-I../../ -I$(NATIVE_CORETRAIL)/include -I$(NATIVE_CORETRAIL)/third_party/glucose-syrup-4.1 -I$(NATIVE_CORETRAIL)/third_party/cardenc -I$(JEMALLOC_ROOT)/include
CPPFLAGS+=-DGlucose=RC2Glucose

# Performance toggles (all opt-in via make VAR=1 unless noted).
ENABLE_LTO?=1
ENABLE_MARCH_NATIVE?=1

ifeq ($(ENABLE_LTO),1)
  CXXFLAGS += -flto=auto
endif

ifeq ($(ENABLE_MARCH_NATIVE),1)
  CXXFLAGS += -march=native
endif

JEMALLOC_LINK_ARGS=$(JEMALLOC_LIB) -lpthread -ldl

OBJDIR=build
OBJS=$(OBJDIR)/ipamircoretrailglue.o \
     $(OBJDIR)/coretrail_solver.o \
     $(OBJDIR)/glucose_backend.o \
     $(OBJDIR)/glucose_solver.o \
     $(OBJDIR)/glucose_options.o \
     $(OBJDIR)/glucose_system.o

all: $(JEMALLOC_LIB) $(TARGET) $(LIBS_FILE)

test-ipamir: $(TARGET) tests/ipamir_smoke.cc
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) tests/ipamir_smoke.cc $(TARGET) $(JEMALLOC_LINK_ARGS) -o $(OBJDIR)/ipamir_smoke
	$(OBJDIR)/ipamir_smoke

test-glucose: tests/glucose_resume.cc | $(OBJDIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) tests/glucose_resume.cc src/core/glucose_backend.cc third_party/glucose-syrup-4.1/core/Solver.cc third_party/glucose-syrup-4.1/utils/Options.cc third_party/glucose-syrup-4.1/utils/System.cc -o $(OBJDIR)/glucose_resume
	$(OBJDIR)/glucose_resume

$(JEMALLOC_LIB):
	@test -d "$(JEMALLOC_ROOT)" || (echo "Missing vendored jemalloc at $(JEMALLOC_ROOT)" >&2; exit 2)
	@cd "$(JEMALLOC_ROOT)" && \
		{ \
			if test -f Makefile; then \
				true; \
			else \
				if test ! -x ./configure; then \
					test -x ./autogen.sh || { echo "Missing jemalloc configure and autogen.sh at $(JEMALLOC_ROOT)" >&2; exit 2; }; \
					./autogen.sh; \
				fi; \
				./configure --disable-shared --enable-static; \
			fi; \
		} && \
		$(MAKE) -j4
	@test -f "$(JEMALLOC_LIB)" || (echo "jemalloc build failed: $(JEMALLOC_LIB) not found" >&2; exit 2)

$(OBJDIR):
	mkdir -p $(OBJDIR)

$(OBJDIR)/ipamircoretrailglue.o: ipamircoretrailglue.cc | $(OBJDIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(OBJDIR)/coretrail_solver.o: $(NATIVE_CORETRAIL)/src/core/coretrail_solver.cc | $(OBJDIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(OBJDIR)/glucose_backend.o: $(NATIVE_CORETRAIL)/src/core/glucose_backend.cc | $(OBJDIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(OBJDIR)/glucose_solver.o: $(NATIVE_CORETRAIL)/third_party/glucose-syrup-4.1/core/Solver.cc | $(OBJDIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(OBJDIR)/glucose_options.o: $(NATIVE_CORETRAIL)/third_party/glucose-syrup-4.1/utils/Options.cc | $(OBJDIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(OBJDIR)/glucose_system.o: $(NATIVE_CORETRAIL)/third_party/glucose-syrup-4.1/utils/System.cc | $(OBJDIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(TARGET): $(OBJS)
	rm -f $@
	$(AR) $(ARFLAGS) $@ $(OBJS)

$(LIBS_FILE): $(JEMALLOC_LIB)
	@echo "$(JEMALLOC_LIB) -lpthread -ldl" > $(LIBS_FILE)

clean:
	rm -rf $(OBJDIR) $(TARGET) $(LIBS_FILE)

.PHONY: all clean test-ipamir test-glucose


compile-coretrail:
	rm -rf native_coretrail/build
	cd native_coretrail && \
	CXXFLAGS="$(CXXFLAGS)" \
	LDFLAGS="$(JEMALLOC_LINK_ARGS)" \
	python3 setup.py build_ext --inplace
