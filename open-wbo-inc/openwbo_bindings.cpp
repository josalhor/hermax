#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "algorithms/Alg_OLL.h"
#include "MaxSATFormula.h"

namespace py = pybind11;
using namespace openwbo;

class OpenWBOInc {
public:
    OpenWBOInc() {
        maxsat_formula = new MaxSATFormula();
        solver = new OLL(0, 1); // verbosity=0, cardinality=1 (Totalizer)
        formula_transferred = false;
    }

    ~OpenWBOInc() {
        if (!formula_transferred && maxsat_formula != nullptr) {
            delete maxsat_formula;
            maxsat_formula = nullptr;
        }
        delete solver;
        // maxsat_formula is deleted by the solver's destructor
    }

    int newVar() {
        maxsat_formula->newVar();
        return maxsat_formula->nVars();
    }

    void addClause(const std::vector<int>& clause, py::object weight_obj) {
        vec<Lit> lits;
        for (int literal : clause) {
            int var = abs(literal) - 1;
            while (var >= maxsat_formula->nVars()) {
                maxsat_formula->newVar();
            }
            lits.push(mkLit(var, literal < 0));
        }

        if (weight_obj.is_none()) {
            maxsat_formula->addHardClause(lits);
        } else {
            long long weight = weight_obj.cast<long long>();
            maxsat_formula->addSoftClause(weight, lits);
        }
    }

    bool solve() {
        solver->loadFormula(maxsat_formula);
        formula_transferred = true;
        solver->search();
        return solver->getModel().size() > 0;
    }

    uint64_t getCost() {
        return solver->getUB();
    }

    bool getValue(int var) {
        // Var is 1-based in the python wrapper
        if (var > 0 && var <= maxsat_formula->nVars()) {
            return solver->getModel()[var - 1] == l_True;
        }
        return false; // Or throw an error
    }

private:
    MaxSATFormula* maxsat_formula;
    MaxSAT* solver;
    bool formula_transferred;
};

PYBIND11_MODULE(openwbo_inc, m) {
    m.doc() = "pybind11 plugin for Open-WBO-Inc";

    py::class_<OpenWBOInc>(m, "OpenWBOInc")
        .def(py::init<>())
        .def("newVar", &OpenWBOInc::newVar)
        .def("addClause", &OpenWBOInc::addClause, py::arg("clause"), py::arg("weight") = py::none())
        .def("solve", &OpenWBOInc::solve)
        .def("getCost", &OpenWBOInc::getCost)
        .def("getValue", &OpenWBOInc::getValue);
}
