#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <optional>
#include <vector>
#include <cmath>
#include <string>
#include "maxhs/core/MaxSolver.h"
#include "maxhs/core/Wcnf.h"
#include "maxhs/utils/Params.h"

#ifdef GLUCOSE
#include "glucose/utils/Options.h"
#else
#include "minisat/utils/Options.h"
#endif

namespace py = pybind11;

// Use Minisat namespace as MaxHS does
#ifdef GLUCOSE
namespace Minisat = Glucose;
#endif

using Minisat::mkLit;
using Minisat::Var;
using Minisat::Lit;
using Minisat::l_True;
using Minisat::l_False;
using Minisat::l_Undef;
using Minisat::parseOptions;

class MaxHSWrapper {
public:
    Wcnf* f;
    MaxHS::MaxSolver* solver;
    int num_vars;
    bool solved;
    int last_status;

    MaxHSWrapper() : f(nullptr), solver(nullptr), num_vars(0), solved(false), last_status(60) {
        // We need to call parseOptions to initialize all the Option objects
        // even if we don't have real argc/argv.
        // int argc = 1;
        // char* argv[] = {(char*)"maxhs_py", NULL};
        // parseOptions(argc, argv, true);
        
        // Now call readOptions to sync Params class with those Option objects
        params.readOptions();
        params.mx_find_mxes = 0;
        // params.preprocess = 0;
        params.verbosity = 0;
        params.sverbosity = 0;
        params.mverbosity = 0;
        // params.conditional_cores = 1;
        // params.init_cores = 1;
        // params.dsjnt_once = 1;
        
        f = new Wcnf();
    }

    ~MaxHSWrapper() {
        if (solver) delete solver;
        if (f) delete f;
    }

    int newVar() {
        return ++num_vars;
    }

    void setNInputVars(int n) {
        if (n > num_vars) num_vars = n;
    }

    void addClause(const std::vector<int>& clause, std::optional<long long> weight = std::nullopt) {
        std::vector<Lit> lits;
        for (int lit : clause) {
            int v = std::abs(lit);
            if (v > num_vars) num_vars = v;
            lits.push_back(mkLit(v - 1, lit < 0));
        }
        
        if (!weight.has_value()) {
            f->addHardClause(lits);
        } else {
            f->addSoftClause(lits, static_cast<Weight>(*weight));
        }
        solved = false;
    }

    bool solve() {
        if (solver) {
            delete solver;
            solver = nullptr;
        }
        
        f->set_dimacs_params(num_vars, f->nHards() + f->nSofts());
        
        solver = new MaxHS::MaxSolver(f);
        solver->solve();
        if (solver->isSolved() && solver->isUnsat()) {
            last_status = 20;  // UNSAT
            solved = false;
        } else if (solver->isSolved() && !solver->isUnsat()) {
            last_status = 30;  // OPTIMUM
            solved = true;
        } else {
            last_status = 60;  // UNKNOWN
            solved = false;
        }
        return solved;
    }

    int solve_status() const {
        return last_status;
    }

    long long getCost() {
        if (!solver) return 0;
        return (long long)(solver->UB() + f->baseCost());
    }

    std::vector<int> getModel() {
        if (!solved || !solver) return {};
        const std::vector<Minisat::lbool>& ubmodel = solver->getBestModel();
        std::vector<int> model;
        for (int i = 0; i < num_vars; ++i) {
            if (i < (int)ubmodel.size()) {
                if (ubmodel[i] == l_True) {
                    model.push_back(i + 1);
                } else {
                    model.push_back(-(i + 1));
                }
            } else {
                model.push_back(-(i + 1));
            }
        }
        return model;
    }
};

PYBIND11_MODULE(maxhs_py, m) {
    m.doc() = "pybind11 plugin for MaxHS";

    py::class_<MaxHSWrapper>(m, "MaxHS")
        .def(py::init<>())
        .def("newVar", &MaxHSWrapper::newVar)
        .def("setNInputVars", &MaxHSWrapper::setNInputVars)
        .def("addClause", &MaxHSWrapper::addClause, py::arg("clause"), py::arg("weight") = std::nullopt)
        .def("solve", &MaxHSWrapper::solve)
        .def("solve_status", &MaxHSWrapper::solve_status)
        .def("getCost", &MaxHSWrapper::getCost)
        .def("getModel", &MaxHSWrapper::getModel);
}
