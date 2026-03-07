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

IPASIRSOLVER ?= minisat220
IPAMIRSOLVER ?= solver2022

#--------------------------------------------------------------------------#
# Compiler flags and library dependencies.
#--------------------------------------------------------------------------#

CC = g++
CFLAGS ?= -Wall -DNDEBUG -O3 -std=c++17

OBJS = Encoding.o Instance.o
DEPS = ../../maxsat/$(IPAMIRSOLVER)/libipamir$(IPAMIRSOLVER).a  ../../sat/$(IPASIRSOLVER)/libipasir$(IPASIRSOLVER).a $(OBJS)
LIBS = -L../../maxsat/$(IPAMIRSOLVER)/ -lipamir$(IPAMIRSOLVER) -L ../../sat/$(IPASIRSOLVER)/ -lipasir$(IPASIRSOLVER)
LIBS += $(shell cat ../../maxsat/$(IPAMIRSOLVER)/LIBS 2>/dev/null)
LIBS += $(shell cat ../../maxsat/$(IPASIRSOLVER)/LIBS 2>/dev/null)
LINK=$(CC)

#--------------------------------------------------------------------------#
# Targets 'all' and 'clean'.
#--------------------------------------------------------------------------#

all: $(TARGET)

clean:
	rm -f $(TARGET) *.o

$(TARGET): $(TARGET).o $(DEPS)
	$(LINK) -o $@ $(TARGET).o $(LIBS) $(OBJS)

#--------------------------------------------------------------------------#
# Local app specific rules.
#--------------------------------------------------------------------------#

%.o: %.cpp
	$(CC) $(CFLAGS) -c -o $@ $<

../../maxsat/$(IPAMIRSOLVER)/libipamir$(IPAMIRSOLVER).a:
	make -C ../../maxsat/$(IPAMIRSOLVER)
