#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "algorithms/Alg_OLL.h"
#include "MaxSATFormula.h"

namespace py = pybind11;
using namespace openwbo;

class OLLEx : public OLL {
public:
    OLLEx(int verbosity, int cardinality) : OLL(verbosity, cardinality) {}

    bool hasModelEx() const { return model.size() != 0; }

    bool getValueEx(int var_ext) const {
        if (var_ext <= 0) throw std::invalid_argument("Variable id must be >= 1");
        int idx = var_ext - 1;
        if (idx >= model.size()) return false;
        return model[idx] == l_True;
    }

    std::vector<int> getModelEx() const {
        std::vector<int> out;
        out.reserve(static_cast<size_t>(model.size()));
        for (int i = 0; i < model.size(); ++i) {
            out.push_back(model[i] == l_True ? (i + 1) : -(i + 1));
        }
        return out;
    }
};

class Loandra {
public:
    Loandra() {
        maxsat_formula = new MaxSATFormula();
        solver = new OLLEx(0, 1); // verbosity=0, cardinality=1 (Totalizer)
        formula_transferred = false;
    }

    ~Loandra() {
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

    void addClause(const std::vector<int>& clause, py::object weight_obj = py::none()) {
        vec<Lit> lits;
        for (int literal : clause) {
            if (literal == 0) throw std::invalid_argument("Literal 0 is invalid");
            int var = std::abs(literal) - 1;
            while (var >= maxsat_formula->nVars()) {
                maxsat_formula->newVar();
            }
            lits.push(mkLit(var, literal < 0));
        }

        if (weight_obj.is_none()) {
            maxsat_formula->addHardClause(lits);
        } else {
            long long weight = weight_obj.cast<long long>();
            if (weight <= 0) throw std::invalid_argument("Soft weight must be positive");
            maxsat_formula->addSoftClause(weight, lits);
        }
    }

    bool solve() {
        solver->loadFormula(maxsat_formula);
        formula_transferred = true;
        solver->search(); // may call exit() in upstream Loandra; subprocess wrapper isolates this
        return solver->hasModelEx();
    }

    uint64_t getCost() {
        return solver->getUB();
    }

    bool getValue(int var) {
        return solver->getValueEx(var);
    }

    std::vector<int> getModel() const {
        return solver->getModelEx();
    }

private:
    MaxSATFormula* maxsat_formula = nullptr;
    OLLEx* solver = nullptr;
    bool formula_transferred = false;
};

PYBIND11_MODULE(loandra, m) {
    m.doc() = "pybind11 plugin for Loandra (OLL path)";

    py::class_<Loandra>(m, "Loandra")
        .def(py::init<>())
        .def("newVar", &Loandra::newVar)
        .def("addClause", &Loandra::addClause, py::arg("clause"), py::arg("weight") = py::none())
        .def("solve", &Loandra::solve)
        .def("getCost", &Loandra::getCost)
        .def("getValue", &Loandra::getValue)
        .def("getModel", &Loandra::getModel);
}
