# Makefile to compile stand-alone shared KINFITTER library

CXX = g++
ROOTCFLAGS = $(shell root-config --cflags)
ROOTLIBS = $(shell root-config --libs)
CXXFLAGS = -fPIC -Wall -O2 -std=c++11 -D_KINFITTER_STANDALONE_ -I../include -I../../external $(ROOTCFLAGS)
LDFLAGS = -shared $(ROOTLIBS)
SRCS = $(wildcard *.cc)
OBJDIR = lib
OBJS = $(patsubst %.cc,$(OBJDIR)/%.o,$(SRCS))
LIB = libKINFITTER.so
INSTALL_DIR = $(HALLD_RECON_HOME)/$(BMS_OSNAME)/lib

all: $(OBJDIR) $(OBJDIR)/$(LIB)

# ensure lib directory exists
$(OBJDIR):
	mkdir -p $(OBJDIR)

# link shared library into lib/
$(OBJDIR)/$(LIB): $(OBJS)
	$(CXX) $(LDFLAGS) -o $@ $(OBJS)
	@echo "Installing $(LIB) to $(INSTALL_DIR)"
	@mkdir -p "$(INSTALL_DIR)"
	@cp "$@" "$(INSTALL_DIR)/"
	@rm -f "$@"

# compile source files into lib/*.o
$(OBJDIR)/%.o: %.cc
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -rf $(OBJDIR)

.PHONY: all clean
