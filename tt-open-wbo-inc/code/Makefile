# VERSION    = core or simp 
# SOLVERNAME = name of the SAT solver
# SOLVERDIR  = subdirectory of the SAT solver
# NSPACE     = namespace of the SAT solver
# 
# e.g. minisat compilation with core version:
#
# VERSION    = core
# SOLVERNAME = "Minisat"
# SOLVERDIR  = minisat
# NSPACE     = Minisat
#

VERSION    = core

# Glucose4_1
#SOLVERNAME = "Glucose4_1"
#SOLVERDIR  = glucose4.1
#NSPACE     = Glucose

# IntelSATSolver
SOLVERNAME = "IntelSATSolver"
SOLVERDIR  = topor
NSPACE     = ToporWrapper
# clause buffer index type: either uint32_t or uint64_t
CLSIND = uint32_t
# compress clause buffer? (can be either false or true; expected to work well only with CLSIND = uint64_t)
COMPRESS = false

# THE REMAINING OF THE MAKEFILE SHOULD BE LEFT UNCHANGED
EXEC       = tt-open-wbo-inc-${SOLVERNAME}
ifeq ($(SOLVERDIR),topor)
	DEPDIR     = topor mtl utils core 
else
	DEPDIR     = mtl utils core 
endif

DEPDIR     +=  ../../encodings ../../algorithms ../../graph ../../classifier ../../clusterings .
MROOT      = $(PWD)/solvers/$(SOLVERDIR)
LFLAGS     += -lgmpxx -lgmp
CFLAGS     = -O3 -Wall -Wno-parentheses -std=c++20 -DNSPACE=$(NSPACE) -DSOLVERNAME=$(SOLVERNAME) -DVERSION=$(VERSION) -DCLSIND=$(CLSIND) -DCOMPRESS=$(COMPRESS)
#CFLAGS     = -g -Wall -Wno-parentheses -std=c++20 -DNSPACE=$(NSPACE) -DSOLVERNAME=$(SOLVERNAME) -DVERSION=$(VERSION)
ifeq ($(VERSION),simp)
DEPDIR     += simp
CFLAGS     += -DSIMP=1 
ifeq ($(SOLVERDIR),glucored)
LFLAGS     += -pthread
CFLAGS     += -DGLUCORED
DEPDIR     += reducer glucored
endif
endif
include $(MROOT)/mtl/template.mk
