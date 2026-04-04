EXEC      = wmaxcdcl
DEPDIR    = mtl utils core

ifeq ($(LS),1)
	DEPDIR += satlike3.0
endif

ifeq ($(MAXHS),1)
	DEPDIR += mhsiface
endif


MROOT = ../

include $(MROOT)/mtl/template.mk
