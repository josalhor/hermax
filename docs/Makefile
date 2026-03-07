# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SPHINXAUTOBUILD ?= sphinx-autobuild
SOURCEDIR     = .
BUILDDIR      = _build
HOST          ?= 127.0.0.1
PORT          ?= 8000
WATCHDIRS     ?= . ../examples ../hermax
IGNOREPATTERNS ?= "*/_build/*" "*/_build_dummy*/*"

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help live pdf Makefile

live:
	@$(SPHINXAUTOBUILD) "$(SOURCEDIR)" "$(BUILDDIR)/html" \
		--host "$(HOST)" \
		--port "$(PORT)" \
		$(foreach d,$(WATCHDIRS),--watch "$(d)") \
		$(foreach p,$(IGNOREPATTERNS),--ignore $(p)) \
		$(SPHINXOPTS) $(O)

pdf:
	@$(SPHINXBUILD) -M latexpdf "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
