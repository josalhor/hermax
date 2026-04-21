import os
import ctypes
from ctypes import c_void_p, c_int, c_ulonglong

LIBNAME  = "libmaxhs.so"
LIBPATH = os.path.abspath(os.path.join(__file__, "..", "..", "build", "dynamic", "lib", LIBNAME))

class Solver(object):

    def __init__(self):
        if not os.path.exists(LIBPATH):
            raise IOError("Shared library not found. Please run 'make lsh' to build the iMaxHS library.")

        self.lib = ctypes.cdll.LoadLibrary(LIBPATH)
        self.lib.ipamir_init.restype = c_void_p
        self.lib.ipamir_init.argtypes = []
        self.lib.ipamir_release.argtypes = [c_void_p]
        self.lib.ipamir_add_hard.argtypes = [c_void_p, c_int]
        self.lib.ipamir_add_soft_lit.argtypes = [c_void_p, c_int, c_ulonglong]
        self.lib.ipamir_assume.argtypes = [c_void_p, c_int]
        self.lib.ipamir_solve.restype = c_int
        self.lib.ipamir_solve.argtypes = [c_void_p]
        self.lib.ipamir_val_obj.restype = c_ulonglong
        self.lib.ipamir_val_obj.argtypes = [c_void_p]
        self.lib.ipamir_val_lit.restype = c_int
        self.lib.ipamir_val_lit.argtypes = [c_void_p, c_int]

        self.solver = self.lib.ipamir_init()
        self.status = 0
        self.n_vars = 0

    def __del__(self):
        if self.solver:
            self.lib.ipamir_release(self.solver)

    def add_clause(self, clause):
        if self.solver:
            for lit in clause:
                self.lib.ipamir_add_hard(self.solver, lit)
                self.n_vars = max(self.n_vars, abs(lit))
            self.lib.ipamir_add_hard(self.solver, 0)

    def add_soft_lit(self, lit, weight):
        if self.solver:
            self.lib.ipamir_add_soft_lit(self.solver, lit, weight)
            self.n_vars = max(self.n_vars, abs(lit))

    def solve(self, assumptions=[]):
        if self.solver:
            for lit in assumptions:
                self.lib.ipamir_assume(self.solver, lit)
                self.n_vars = max(self.n_vars, abs(lit))
            self.status = self.lib.ipamir_solve(self.solver)
            return self.status

    def get_model(self):
        if self.solver and (self.status == 20 or self.status == 30):
            model = [ self.lib.ipamir_val_lit(self.solver, var) for var in range(1,self.n_vars+1) ]
            return model

    def get_obj_val(self):
        if self.solver and (self.status == 20 or self.status == 30):
            return self.lib.ipamir_val_obj(self.solver)