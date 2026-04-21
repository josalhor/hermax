###################################################################################################
#  make			 "for release version"
#  make d		 "debug version"
#  make p		 "profiling version"
#  make clean   	 "remove object files and executable"
###################################################################################################
.PHONY:	r d p lr ld lp ipamir all install install-bin clean distclean
all: r

## Configurable options ###########################################################################

## Cplex library location (configure these variables)
LINUX_CPLEXLIBDIR   ?= /home/jsh7/opt/cplex/cplex/lib/x86-64_linux/static_pic
LINUX_CPLEXINCDIR   ?= /home/jsh7/opt/cplex/cplex/include

## Cplex libary on mac vm
LINUXVM_CPLEXLIBDIR   ?= /home/andreasn/opt/ibm/ILOG/CPLEX_Studio1210/cplex/lib/x86-64_linux/static_pic
LINUXVM_CPLEXINCDIR   ?= /home/andreasn/opt/ibm/ILOG/CPLEX_Studio1210/cplex/include

## If you want to build on macos
DARWIN_CPLEXLIBDIR   ?= /home/andreasn/opt/ibm/ILOG/CPLEX_Studio1210/cplex/lib/x86-64_linux/static_pic
DARWIN_CPLEXINCDIR   ?= /home/andreasn/opt/ibm/ILOG/CPLEX_Studio1210/cplex/include

ifeq "$(shell uname)" "Linux"
CPLEXLIBDIR   =$(LINUX_CPLEXLIBDIR)
CPLEXINCDIR   =$(LINUX_CPLEXINCDIR)
endif
ifeq "$(shell uname)" "Darwin"
CPLEXLIBDIR   =$(DARWIN_CPLEXLIBDIR)
CPLEXINCDIR   =$(DARWIN_CPLEXINCDIR)
endif
ifeq "$(shell hostname)" "ubuntu-vm"
CPLEXLIBDIR   =$(LINUXVM_CPLEXLIBDIR)
CPLEXINCDIR   =$(LINUXVM_CPLEXINCDIR)
endif

# Directory to store object files, libraries, executables, and dependencies:
BUILD_DIR      ?= build

# Include debug-symbols in release builds?
#MAXHS_RELSYM ?= -g

MAXHS_REL    ?= -O3 -DNDEBUG -DNCONTRACTS -DNTRACING -DQUIET
#MAXHS_REL    += -DLOGGING
#MAXHS_DEB    ?= -O0 -DDEBUG -D_GLIBCXX_DEBUG -ggdb
MAXHS_DEB    ?= -O0 -DDEBUG -ggdb
MAXHS_PRF    ?= -O3 -DNDEBUG
MAXHS_FPIC   ?= -fPIC

ifneq "$(CXX)" "clang++"
MAXHS_REL    += -flto 
endif
# Target file names
MAXHS      = maxhs#       Name of Maxhs main executable.
MAXHS_SLIB = lib$(MAXHS).a#  Name of Maxhs static library.
MAXHS_DLIB = lib$(MAXHS).so
IPAMIR_LIB = libipamir$(MAXHS).a# Name of IPAMIR static library.

#-DIL_STD is a IBM/CPLEX issue

MAXHS_CXXFLAGS = -DIL_STD -I. -I$(CPLEXINCDIR)
MAXHS_CXXFLAGS += -Wall -Wno-unused-parameter -Wno-parentheses -Wextra -Wno-deprecated
MAXHS_CXXFLAGS += -std=c++14

MAXHS_LDFLAGS  = -Wall -lz -L$(CPLEXLIBDIR) -lcplex -lpthread -ldl -flto

ECHO=@echo

ifeq ($(VERB),)
VERB=@
else
VERB=
endif

MAXHS_SRCS = $(wildcard maxhs/core/*.cc) $(wildcard maxhs/ifaces/*.cc) $(wildcard maxhs/utils/*.cc) \
             $(wildcard ipamir/*.cc) $(wildcard minisat/utils/*.cc)
SATSOLVER_SRCS = $(wildcard cadical/src/*.cpp)

OBJS = $(filter-out %Main.o, $(MAXHS_SRCS:.cc=.o))
ALLOBJS = $(MAXHS_SRCS:.cc=.o)
OBJS += $(filter-out %cadical.o %mobical.o, $(SATSOLVER_SRCS:.cpp=.o))
ALLOBJS += $(SATSOLVER_SRCS:.cpp=.o)

r:	$(BUILD_DIR)/release/bin/$(MAXHS)
d:	$(BUILD_DIR)/debug/bin/$(MAXHS)
p:	$(BUILD_DIR)/profile/bin/$(MAXHS)
sh:	$(BUILD_DIR)/dynamic/bin/$(MAXHS)

lr:	$(BUILD_DIR)/release/lib/$(MAXHS_SLIB)
ld:	$(BUILD_DIR)/debug/lib/$(MAXHS_SLIB)
lp:	$(BUILD_DIR)/profile/lib/$(MAXHS_SLIB)
lsh:	$(BUILD_DIR)/dynamic/lib/$(MAXHS_DLIB)

ipamir: $(BUILD_DIR)/release/lib/$(IPAMIR_LIB)

## Build-type Compile-flags:
$(BUILD_DIR)/release/%.o:           MAXHS_CXXFLAGS +=$(MAXHS_REL) $(MAXHS_RELSYM)
$(BUILD_DIR)/debug/%.o:				MAXHS_CXXFLAGS +=$(MAXHS_DEB)
$(BUILD_DIR)/profile/%.o:			MAXHS_CXXFLAGS +=$(MAXHS_PRF) -pg
$(BUILD_DIR)/dynamic/%.o:			MAXHS_CXXFLAGS +=$(MAXHS_REL) $(MAXHS_FPIC)

## Build-type Link-flags:
$(BUILD_DIR)/profile/bin/$(MAXHS):		MAXHS_LDFLAGS += -pg --static
ifeq "$(shell uname)" "Linux"
$(BUILD_DIR)/release/bin/$(MAXHS):		MAXHS_LDFLAGS += -z muldefs
endif
$(BUILD_DIR)/release/bin/$(MAXHS):		MAXHS_LDFLAGS += $(MAXHS_RELSYM)

## Executable dependencies
$(BUILD_DIR)/release/bin/$(MAXHS):	 	$(BUILD_DIR)/release/maxhs/core/Main.o $(BUILD_DIR)/release/lib/$(MAXHS_SLIB)
$(BUILD_DIR)/debug/bin/$(MAXHS):	 	$(BUILD_DIR)/debug/Main.o $(BUILD_DIR)/debug/lib/$(MAXHS_SLIB)
$(BUILD_DIR)/profile/bin/$(MAXHS):	 	$(BUILD_DIR)/profile/Main.o $(BUILD_DIR)/profile/lib/$(MAXHS_SLIB)
$(BUILD_DIR)/dynamic/bin/$(MAXHS):	 	$(BUILD_DIR)/dynamic/maxhs/core/Main.o $(BUILD_DIR)/dynamic/lib/$(MAXHS_DLIB)

## Library dependencies
$(BUILD_DIR)/release/lib/$(MAXHS_SLIB):	$(foreach o,$(OBJS),$(BUILD_DIR)/release/$(o))
$(BUILD_DIR)/debug/lib/$(MAXHS_SLIB):	$(foreach o,$(OBJS),$(BUILD_DIR)/debug/$(o))
$(BUILD_DIR)/profile/lib/$(MAXHS_SLIB):	$(foreach o,$(OBJS),$(BUILD_DIR)/profile/$(o))
$(BUILD_DIR)/dynamic/lib/$(MAXHS_DLIB):	$(foreach o,$(OBJS),$(BUILD_DIR)/dynamic/$(o))
$(BUILD_DIR)/release/lib/$(IPAMIR_LIB): $(BUILD_DIR)/release/lib/$(MAXHS_SLIB)

## Compile rules
$(BUILD_DIR)/release/%.o:	%.cc
	$(ECHO) Compiling: $@
	$(VERB) mkdir -p $(dir $@)
	$(VERB) $(CXX) $(MAXHS_CXXFLAGS) $(CXXFLAGS) -c -o $@ $< -MMD -MF $(BUILD_DIR)/release/$*.d
$(BUILD_DIR)/release/%.o:	%.cpp
	$(ECHO) Compiling: $@
	$(VERB) mkdir -p $(dir $@)
	$(VERB) $(CXX) $(MAXHS_CXXFLAGS) $(CXXFLAGS) -c -o $@ $< -MMD -MF $(BUILD_DIR)/release/$*.d

$(BUILD_DIR)/profile/%.o:	%.cc
	$(ECHO) Compiling: $@
	$(VERB) mkdir -p $(dir $@)
	$(VERB) $(CXX) $(MAXHS_CXXFLAGS) $(CXXFLAGS) -c -o $@ $< -MMD -MF $(BUILD_DIR)/profile/$*.d
$(BUILD_DIR)/profile/%.o:	%.cpp
	$(ECHO) Compiling: $@
	$(VERB) mkdir -p $(dir $@)
	$(VERB) $(CXX) $(MAXHS_CXXFLAGS) $(CXXFLAGS) -c -o $@ $< -MMD -MF $(BUILD_DIR)/release/$*.d

$(BUILD_DIR)/debug/%.o:	%.cc
	$(ECHO) Compiling: $@
	$(VERB) mkdir -p $(dir $@)
	$(VERB) $(CXX) $(MAXHS_CXXFLAGS) $(CXXFLAGS) -c -o $@ $< -MMD -MF $(BUILD_DIR)/debug/$*.d
$(BUILD_DIR)/debug/%.o:	%.cpp
	$(ECHO) Compiling: $@
	$(VERB) mkdir -p $(dir $@)
	$(VERB) $(CXX) $(MAXHS_CXXFLAGS) $(CXXFLAGS) -c -o $@ $< -MMD -MF $(BUILD_DIR)/release/$*.d

$(BUILD_DIR)/dynamic/%.o:	%.cc
	$(ECHO) Compiling: $@
	$(VERB) mkdir -p $(dir $@)
	$(VERB) $(CXX) $(MAXHS_CXXFLAGS) $(CXXFLAGS) -c -o $@ $< -MMD -MF $(BUILD_DIR)/dynamic/$*.d
$(BUILD_DIR)/dynamic/%.o:	%.cpp
	$(ECHO) Compiling: $@
	$(VERB) mkdir -p $(dir $@)
	$(VERB) $(CXX) $(MAXHS_CXXFLAGS) $(CXXFLAGS) -c -o $@ $< -MMD -MF $(BUILD_DIR)/release/$*.d


## Linking rule
$(BUILD_DIR)/release/bin/$(MAXHS) $(BUILD_DIR)/debug/bin/$(MAXHS) $(BUILD_DIR)/profile/bin/$(MAXHS) $(BUILD_DIR)/dynamic/bin/$(MAXHS):
	$(ECHO) Linking Binary: $@
	$(VERB) mkdir -p $(dir $@)
	$(VERB) $(CXX) $^ $(MAXHS_LDFLAGS) -o $@

## Static Library rule
%/lib/$(MAXHS_SLIB):
	$(ECHO) Linking Static Library: $@
	$(VERB) mkdir -p $(dir $@)
	$(VERB) $(AR) -rcs $@ $^

## Shared Library rule
$(BUILD_DIR)/dynamic/lib/$(MAXHS_DLIB):
	$(ECHO) Linking Shared Library: $@
	$(VERB) mkdir -p $(dir $@)
	$(VERB) $(CXX) $^ $(MAXHS_LDFLAGS) -o $@ -shared -Wl,-soname,$(MAXHS_DLIB)

%/lib/$(IPAMIR_LIB):
	$(ECHO) Linking IPAMIR Library: $@
	$(VERB) cp $(BUILD_DIR)/release/lib/$(MAXHS_SLIB) $(BUILD_DIR)/release/lib/$(IPAMIR_LIB)
	$(VERB) $(AR) -r $(BUILD_DIR)/release/lib/$(IPAMIR_LIB) $(BUILD_DIR)/release/ipamir/IpamirMaxHS.o

clean:
	rm -f $(foreach t, release debug profile dynamic, $(foreach o, $(ALLOBJS), $(BUILD_DIR)/$t/$o)) \
	$(foreach t, release debug profile dynamic, $(foreach d, $(ALLOBJS:.o=.d), $(BUILD_DIR)/$t/$d)) \
	$(foreach t, release debug profile dynamic, $(BUILD_DIR)/$t/bin/$(MAXHS))\
	$(foreach t, release debug profile, $(BUILD_DIR)/$t/lib/$(MAXHS_SLIB)) \
	$(BUILD_DIR)/dynamic/lib/$(MAXHS_DLIB)

## Include generated dependencies
DEPS = $(foreach b, release, $(foreach d, $(ALLOBJS:.o=.d), $(BUILD_DIR)/$b/$d))

-include $(DEPS)
