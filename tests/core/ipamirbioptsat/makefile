#--------------------------------------------------------------------------#
# The target name should be the name of this app, which actually should be
# the same as the name of this directory.
#--------------------------------------------------------------------------#

TARGET=$(shell basename "`pwd`")

#--------------------------------------------------------------------------#
# The environment variable 'IPAMIRSOLVER' is used to locate the MaxSAT solver
# library from ../../maxsat/$(IPAMIRSOLVER). For testing purposes we set it to
# the non-incremental MaxSAT solver 'solver2022' which is compiled using
# 'minisat220' as the SAT solver.
#--------------------------------------------------------------------------#

IPAMIRSOLVER ?= solver2022
IPASIRSOLVER ?= minisat220

#--------------------------------------------------------------------------#
# Compiler flags and library dependencies.
#--------------------------------------------------------------------------#

CC = g++
CFLAGS ?= -Wall -DNDEBUG -O3 -std=c++17

DEPS = ../../maxsat/$(IPAMIRSOLVER)/libipamir$(IPAMIRSOLVER).a \
	../../sat/$(IPASIRSOLVER)/libipasir$(IPASIRSOLVER).a \
	totalizer.o
LIBS = -L../../maxsat/$(IPAMIRSOLVER)/ -lipamir$(IPAMIRSOLVER)
LIBS += -L../../sat/$(IPASIRSOLVER)/ -lipasir$(IPASIRSOLVER)
LIBS += $(shell cat ../../maxsat/$(IPAMIRSOLVER)/LIBS 2>/dev/null)
LIBS += $(shell cat ../../sat/$(IPASIRSOLVER)/LIBS 2>/dev/null)
OBJS = totalizer.o
LINK=$(CC)

#--------------------------------------------------------------------------#
# Targets 'all' and 'clean'.
#--------------------------------------------------------------------------#

all: $(TARGET)

clean:
	rm -f $(TARGET) *.o
	rm -rf pblib

$(TARGET): $(TARGET).o $(DEPS)
	$(LINK) -o $@ $(TARGET).o $(OBJS) $(LIBS)

#--------------------------------------------------------------------------#
# Local app specific rules.
#--------------------------------------------------------------------------#

$(TARGET).o: $(TARGET).cpp totalizer.hpp makefile
	$(CC) $(CFLAGS) -c $(TARGET).cpp

totalizer.o: totalizer.cpp totalizer.hpp makefile
	$(CC) $(CFLAGS) -c totalizer.cpp

../../maxsat/$(IPAMIRSOLVER)/libipamir$(IPAMIRSOLVER).a:
	make -C ../../maxsat/$(IPAMIRSOLVER)

../../sat/$(IPASIRSOLVER)/libipasir$(IPASIRSOLVER).a:
	make -C ../../sat/$(IPASIRSOLVER)
