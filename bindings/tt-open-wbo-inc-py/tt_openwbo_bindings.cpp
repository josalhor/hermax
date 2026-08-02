#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "../../solvers/tt-open-wbo-inc/code/MaxSATFormulaExtended.h"
#include "../../solvers/tt-open-wbo-inc/code/MaxTypes.h"
#include "../../solvers/tt-open-wbo-inc/code/Torc.h"
#include "../../solvers/tt-open-wbo-inc/code/algorithms/Alg_LinearSU_Clustering.h"
#include "../../solvers/tt-open-wbo-inc/code/algorithms/Alg_OBV.h"

namespace py = pybind11;
using namespace openwbo;

namespace {

class ModelAccessOBV : public OBV {
public:
    using OBV::OBV;

    vec<lbool>& exposedModel() {
        return this->model;
    }
};

class ModelAccessLinearSUClustering : public LinearSUClustering {
public:
    using LinearSUClustering::LinearSUClustering;

    vec<lbool>& exposedModel() {
        return this->model;
    }
};

enum class SolverKind {
    Obv,
    LinearSUClustering,
};

void apply_best_defaults(MaxSATFormula *formula) {
    Torc::Instance()->SetPrintEveryModel(0);

    if (formula == nullptr) {
        return;
    }

    const int total_clauses = formula->nSoft() + formula->nHard();
    const double soft_fraction =
        total_clauses == 0 ? 0.0 : static_cast<double>(formula->nSoft()) / static_cast<double>(total_clauses);

    if (soft_fraction > Torc::Instance()->GetOptimisticMaxSoftFraction()) {
        Torc::Instance()->SetPolOptimistic(false);
    }
    if (soft_fraction > Torc::Instance()->GetConservativeMaxSoftFraction()) {
        Torc::Instance()->SetPolConservative(false);
    }

    if (formula->getProblemType() == _UNWEIGHTED_) {
        Torc::Instance()->SetTargetVarsBumpVal(50);
        Torc::Instance()->SetBumpRelWeights(false);
        Torc::Instance()->SetTargetBumpMaxRandVal(0);
        Torc::Instance()->SetMsMutationClasses(0);
        Torc::Instance()->SetChrono(100);
        Torc::Instance()->SetMsObvStrat(7);
        Torc::Instance()->SetSatlikeInitTimeThr(30);
        Torc::Instance()->SetSatlikeInvsThr(5);
    } else {
        Torc::Instance()->SetSatlikeTimeThr(30);
        Torc::Instance()->toporParams.insert(Torc::Instance()->toporParams.begin(), std::make_pair("/mode/value", 5.0));
        Torc::Instance()->SetMsModelPerSecThr(0.25);
        Torc::Instance()->SetMsPropPerModelThr(100000000);
    }
}

MaxSAT *build_best_solver(MaxSATFormula *formula, SolverKind &kind) {
    apply_best_defaults(formula);

    MaxSAT *solver = nullptr;
    if (formula->getProblemType() == _UNWEIGHTED_) {
        kind = SolverKind::Obv;
        solver = new ModelAccessOBV(_VERBOSITY_MINIMAL_, _CARD_MTOTALIZER_, 1000, INT32_MAX, true);
    } else {
        kind = SolverKind::LinearSUClustering;
        solver = new ModelAccessLinearSUClustering(
            _VERBOSITY_MINIMAL_,
            true,
            _CARD_TOTALIZER_,
            _PB_GTE_,
            ClusterAlg::_DIVISIVE_,
            Statistics::_MEAN_,
            100000);
    }

    solver->loadFormula(formula);
    if (formula->getProblemType() != _UNWEIGHTED_) {
        static_cast<ModelAccessLinearSUClustering *>(solver)->initializeCluster();
    }
    solver->setPrintModel(true);
    return solver;
}

vec<lbool>& exposed_model(MaxSAT *solver, SolverKind kind) {
    if (kind == SolverKind::Obv) {
        return static_cast<ModelAccessOBV *>(solver)->exposedModel();
    }
    return static_cast<ModelAccessLinearSUClustering *>(solver)->exposedModel();
}

} // namespace

class TTOpenWBOInc {
public:
    TTOpenWBOInc() {
        maxsat_formula = new MaxSATFormulaExtended();
        solver = nullptr;
        formula_transferred = false;
        solver_kind = SolverKind::Obv;
    }

    ~TTOpenWBOInc() {
        if (!formula_transferred && maxsat_formula != nullptr) {
            delete maxsat_formula;
            maxsat_formula = nullptr;
        }
        delete solver;
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
        if (solver == nullptr) {
            solver = build_best_solver(maxsat_formula, solver_kind);
            formula_transferred = true;
        }
        solver->search();
        return exposed_model(solver, solver_kind).size() > 0;
    }

    uint64_t getCost() {
        return solver->getUB();
    }

    bool getValue(int var) {
        if (var > 0 && var <= maxsat_formula->nVars()) {
            return exposed_model(solver, solver_kind)[var - 1] == l_True;
        }
        return false;
    }

private:
    MaxSATFormulaExtended *maxsat_formula;
    MaxSAT *solver;
    bool formula_transferred;
    SolverKind solver_kind;
};

PYBIND11_MODULE(tt_openwbo_inc, m) {
    m.doc() = "pybind11 plugin for TT-Open-WBO-Inc";

    py::class_<TTOpenWBOInc>(m, "TTOpenWBOInc")
        .def(py::init<>())
        .def("newVar", &TTOpenWBOInc::newVar)
        .def("addClause", &TTOpenWBOInc::addClause, py::arg("clause"), py::arg("weight") = py::none())
        .def("solve", &TTOpenWBOInc::solve)
        .def("getCost", &TTOpenWBOInc::getCost)
        .def("getValue", &TTOpenWBOInc::getValue);
}
