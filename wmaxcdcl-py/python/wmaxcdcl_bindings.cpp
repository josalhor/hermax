#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <stdexcept>
#include <vector>
#include <cstdint>

#include "simp/SimpSolver.h"

namespace py = pybind11;

class WMaxCDCLNative {
public:
    Minisat::SimpSolver solver;
    bool prepared = false;
    int n_input_vars = 0;

    WMaxCDCLNative() {
        reset_maxsat_state();
    }

    void reset_maxsat_state() {
        solver.parsing = false;
        solver.instanceType = 1;           // weighted MaxSAT / WCNF mode
        solver.hardWeight = INT64_MAX;     // explicit hard clauses use weight=0 -> hardWeight
        solver.initUB = INT64_MAX;
        solver.initLB = 0;
        solver.UB = INT64_MAX;
        solver.nbOriVars = 0;
        solver.nbOrignalVars = 0;
        prepared = false;
    }

    void ensure_var(int v1) {
        if (v1 <= 0) return;
        bool grew = false;
        while (solver.nVars() < v1) {
            solver.newVar();
            grew = true;
        }
        if (v1 > n_input_vars) {
            n_input_vars = v1;
            solver.nbOriVars = n_input_vars;
            solver.nbOrignalVars = n_input_vars;
        }
        if (grew) prepared = false;
    }

    int newVar(bool decisionVar = true) {
        (void)decisionVar;  // upstream API accepts flags, but default behavior is fine here
        int v0 = solver.newVar();
        int v1 = v0 + 1;
        if (v1 > n_input_vars) {
            n_input_vars = v1;
            solver.nbOriVars = n_input_vars;
            solver.nbOrignalVars = n_input_vars;
        }
        prepared = false;
        return v1;
    }

    bool addClause(const std::vector<int>& clause, py::object weight_obj = py::none()) {
        Minisat::vec<Minisat::Lit> ps;
        ps.clear();
        for (int lit : clause) {
            if (lit == 0) throw std::invalid_argument("literal 0 is invalid");
            ensure_var(std::abs(lit));
            int v = std::abs(lit) - 1;
            bool s = (lit < 0);
            ps.push(Minisat::mkLit(v, s));
        }

        prepared = false;
        if (!weight_obj.is_none()) {
            long long w = weight_obj.cast<long long>();
            if (w <= 0) throw std::invalid_argument("weight must be positive");
            if (w > INT64_MAX) throw std::overflow_error("weight must be <= INT64_MAX");
            bool ok = solver.addClause_(ps, static_cast<int64_t>(w));
            if (ok) {
                solver.totalWeight += static_cast<int64_t>(w);
            }
            return ok;
        }
        // Hard clause path: SimpSolver maps weight=0 to hardWeight.
        return solver.addClause_(ps, 0);
    }

    void setNInputVars(unsigned int n) {
        ensure_var(static_cast<int>(n));
        n_input_vars = static_cast<int>(n);
        solver.nbOriVars = static_cast<int>(n);
        solver.nbOrignalVars = static_cast<int>(n);
    }

    void prepare() {
        if (prepared) return;
        if (solver.totalWeight >= 0 && solver.totalWeight < (INT64_MAX - 1)) {
            // Use a realistic WCNF top weight (sum soft + 1). This matches
            // standard WCNF semantics more closely than INT64_MAX and avoids
            // internal paths that appear to assume a finite top.
            solver.hardWeight = solver.totalWeight + 1;
            solver.UB = solver.hardWeight;
        }
        solver.parsing = false;
        solver.nbOriVars = n_input_vars;
        solver.nbOrignalVars = n_input_vars;
        prepared = true;
    }

    bool solve(py::object assumptions_obj = py::none()) {
        Minisat::vec<Minisat::Lit> assumps;
        if (!assumptions_obj.is_none()) {
            auto assumptions = assumptions_obj.cast<std::vector<int>>();
            for (int lit : assumptions) {
                if (lit == 0) throw std::invalid_argument("assumption literal 0 is invalid");
                ensure_var(std::abs(lit));
                int v = std::abs(lit) - 1;
                bool s = (lit < 0);
                assumps.push(Minisat::mkLit(v, s));
            }
        }
        prepare();
        return solver.solve(assumps, true, false);
    }

    long long getCost() const {
        return static_cast<long long>(solver.optimal);
    }

    bool getValue(int lit) const {
        if (lit == 0) throw std::invalid_argument("literal 0 is invalid");
        int v = std::abs(lit) - 1;
        if (v < 0 || v >= solver.model.size()) return false;
        const auto mv = solver.model[v];
        bool val = (mv == l_True);
        return lit > 0 ? val : !val;
    }

    std::vector<int> getModel() const {
        std::vector<int> model;
        int n = solver.nbOrignalVars > 0 ? solver.nbOrignalVars : solver.model.size();
        model.reserve(static_cast<size_t>(n));
        for (int i = 0; i < n; ++i) {
            if (i < solver.model.size() && solver.model[i] == l_True)
                model.push_back(i + 1);
            else
                model.push_back(-(i + 1));
        }
        return model;
    }
};

PYBIND11_MODULE(wmaxcdcl, m) {
    m.doc() = "pybind11 bindings for WMaxCDCL (plain solver path, no SCIP/MaxHS)";

    py::class_<WMaxCDCLNative>(m, "WMaxCDCL")
        .def(py::init<>())
        .def("newVar", &WMaxCDCLNative::newVar, py::arg("decisionVar") = true)
        .def("addClause", &WMaxCDCLNative::addClause, py::arg("clause"), py::arg("weight") = py::none())
        .def("setNInputVars", &WMaxCDCLNative::setNInputVars)
        .def("prepare", &WMaxCDCLNative::prepare)
        .def("solve", &WMaxCDCLNative::solve, py::arg("assumptions") = py::none())
        .def("getCost", &WMaxCDCLNative::getCost)
        .def("getValue", &WMaxCDCLNative::getValue)
        .def("getModel", &WMaxCDCLNative::getModel);
}
