##
##  Template makefile for Standard, Profile, Debug, Release, and Release-static versions
##
##    eg: "make rs" for a statically linked release version.
##        "make d"  for a debug version (no optimizations).
##        "make"    for the standard version (optimized, but with debug information and assertions active)

## Cplex library location (configure these variables)
LINUX_CPLEXLIBDIR   ?= /scratch/maxsat/extsolvers/cplex/cplex/lib/x86-64_linux/static_pic
LINUX_CPLEXINCDIR   ?= /scratch/maxsat/extsolvers/cplex/cplex/include

#
#If you want to build on macos
DARWIN_CPLEXLIBDIR   ?= /Applications/CPLEX_Studio221/cplex/lib/x86-64_osx/static_pic/
DARWIN_CPLEXINCDIR   ?= /Applications/CPLEX_Studio221/cplex/include

ifeq "$(shell uname)" "Linux"
CPLEXLIBDIR   =$(LINUX_CPLEXLIBDIR)
CPLEXINCDIR   =$(LINUX_CPLEXINCDIR)
endif
ifeq "$(shell uname)" "Darwin"
CPLEXLIBDIR   =$(DARWIN_CPLEXLIBDIR)
CPLEXINCDIR   =$(DARWIN_CPLEXINCDIR)
endif

PWD        = $(shell pwd)
EXEC      ?= $(notdir $(PWD))

CSRCS      = $(wildcard $(PWD)/*.cc) 
DSRCS      = $(foreach dir, $(DEPDIR), $(filter-out $(MROOT)/$(dir)/Main.cc, $(wildcard $(MROOT)/$(dir)/*.cc)))
CHDRS      = $(wildcard $(PWD)/*.h)
COBJS      = $(CSRCS:.cc=.o) $(DSRCS:.cc=.o)

PCOBJS     = $(addsuffix p,  $(COBJS))
DCOBJS     = $(addsuffix d,  $(COBJS))
RCOBJS     = $(addsuffix r,  $(COBJS))


#Custom WMaxCDCLflags to enable or disable functionalities
#All stated negative so that by default no extra flag means default solver
NO_ADDPB := 0
ALWAYS_ADDPB := 0
NO_LA := 0
ALWAYS_LA := 0
NO_HARDEN := 0
NO_HARDEN_LA := 0
UPDOWN := 0

CXX       ?= g++
CFLAGS    ?= -Wall -Wno-parentheses -std=c++14
LFLAGS    ?= -Wall

COPTIMIZE ?= -O3

CFLAGS    += -I$(MROOT)  -D __STDC_LIMIT_MACROS -D __STDC_FORMAT_MACROS
LFLAGS    += -lz

ifeq ($(MAXHS),1)
	CFLAGS += -D FLAG_MAXHS -I$(MROOT)/mhs
	LFLAGS += -L$(MROOT)/mhs/build/release/lib -lmaxhs  -L$(CPLEXLIBDIR)  -lcplex -lpthread -ldl
endif

ifeq ($(LS),1)
	CFLAGS+= -D FLAG_LS
endif



ifeq ($(NO_ADDPB),1)
	CFLAGS+= -D FLAG_NO_ADDPB
	EXEC:=$(EXEC)_noaddpb
endif
ifeq ($(ALWAYS_ADDPB),1)
	CFLAGS+= -D FLAG_ALWAYS_ADDPB
	EXEC:=$(EXEC)_alwaysaddpb
endif
ifeq ($(NO_LA),1)
	CFLAGS+= -D FLAG_NO_LA
	EXEC:=$(EXEC)_nola
endif
ifeq ($(ALWAYS_LA),1)
     CFLAGS+= -D FLAG_ALWAYS_LA
     EXEC:=$(EXEC)_alwaysla
endif
ifeq ($(NO_HARDEN),1)
	CFLAGS+= -D FLAG_NO_HARDEN
	EXEC:=$(EXEC)_noharden
endif
ifeq ($(NO_HARDEN_LA),1)
	CFLAGS+= -D FLAG_NO_HARDEN_LA
	EXEC:=$(EXEC)_nohardenla
endif
ifeq ($(UPDOWN),1)
	CFLAGS+= -D FLAG_UPDOWN
	EXEC:=$(EXEC)_updown
endif



.PHONY : s p d r rs clean cleanobj

s:	$(EXEC)
p:	$(EXEC)_profile
d:	$(EXEC)_debug
r:	$(EXEC)_release
rs:	$(EXEC)_static

libs:	lib$(LIB)_standard.a
libp:	lib$(LIB)_profile.a
libd:	lib$(LIB)_debug.a
libr:	lib$(LIB)_release.a

## Compile options
%.o:			CFLAGS +=$(COPTIMIZE) -g -D DEBUG
%.op:			CFLAGS +=$(COPTIMIZE) -pg -g -D NDEBUG
%.od:			CFLAGS +=-O0 -g -D DEBUG
%.or:			CFLAGS +=$(COPTIMIZE) -g -D NDEBUG

## Link options
$(EXEC):		LFLAGS += -g
$(EXEC)_profile:	LFLAGS += -g -pg
$(EXEC)_debug:		LFLAGS += -g
#$(EXEC)_release:	LFLAGS += ...
$(EXEC)_static:		LFLAGS += --static

## Dependencies
$(EXEC):		$(COBJS)
$(EXEC)_profile:	$(PCOBJS)
$(EXEC)_debug:		$(DCOBJS)
$(EXEC)_release:	$(RCOBJS)
$(EXEC)_static:		$(RCOBJS)

lib$(LIB)_standard.a:	$(filter-out */Main.o,  $(COBJS))
lib$(LIB)_profile.a:	$(filter-out */Main.op, $(PCOBJS))
lib$(LIB)_debug.a:	$(filter-out */Main.od, $(DCOBJS))
lib$(LIB)_release.a:	$(filter-out */Main.or, $(RCOBJS))


## Build rule
%.o %.op %.od %.or:	%.cc
	@echo Compiling: $(subst $(MROOT)/,,$@)
	@$(CXX) $(CFLAGS) -c -o $@ $<

## Linking rules (standard/profile/debug/release)
$(EXEC) $(EXEC)_profile $(EXEC)_debug $(EXEC)_release $(EXEC)_static:
	@echo Linking: "$@ ( $(foreach f,$^,$(subst $(MROOT)/,,$f)) )"
	@$(CXX) $^ $(LFLAGS) -o $@

## Library rules (standard/profile/debug/release)
lib$(LIB)_standard.a lib$(LIB)_profile.a lib$(LIB)_release.a lib$(LIB)_debug.a:
	@echo Making library: "$@ ( $(foreach f,$^,$(subst $(MROOT)/,,$f)) )"
	@$(AR) -rcsv $@ $^

## Library Soft Link rule:
libs libp libd libr:
	@echo "Making Soft Link: $^ -> lib$(LIB).a"
	@ln -sf $^ lib$(LIB).a

## Clean rule
clean:
	@rm -f $(EXEC)*  \
	  $(COBJS) $(PCOBJS) $(DCOBJS) $(RCOBJS) *.core depend.mk

## Clean only object, not binaries
cleanobj:
	@rm -f  $(COBJS) $(PCOBJS) $(DCOBJS) $(RCOBJS) *.core depend.mk

## Make dependencies
depend.mk: $(CSRCS) $(CHDRS)
	@echo Making dependencies
	@$(CXX) $(CFLAGS) -I$(MROOT) \
	   $(CSRCS) -MM | sed 's|\(.*\):|$(PWD)/\1 $(PWD)/\1r $(PWD)/\1d $(PWD)/\1p:|' > depend.mk
	@for dir in $(DEPDIR); do \
	      if [ -r $(MROOT)/$${dir}/depend.mk ]; then \
		  echo Depends on: $${dir}; \
		  cat $(MROOT)/$${dir}/depend.mk >> depend.mk; \
	      fi; \
	  done

-include $(MROOT)/mtl/config.mk
-include depend.mk
