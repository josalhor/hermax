#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "algorithms/Alg_BLS.h"
#include "MaxSATFormula.h"

#include <algorithm>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <unordered_map>
#include <vector>

namespace py = pybind11;
using namespace openwbo;

struct WeightOpt {
    bool has_val;
    long long val;
    WeightOpt() : has_val(false), val(0) {}
    explicit WeightOpt(long long v) : has_val(true), val(v) {}
    bool has_value() const { return has_val; }
    long long operator*() const { return val; }
};

using ClauseRec = std::pair<std::vector<int>, WeightOpt>;

static inline void append_clause(MaxSATFormula* F,
                                 const std::vector<int>& clause_ext,
                                 const WeightOpt& wopt) {
    vec<Lit> lits;
    lits.capacity(clause_ext.size());
    for (int lit : clause_ext) {
        if (lit == 0) throw std::invalid_argument("Literal 0 is invalid");
        const int v0 = std::abs(lit) - 1;
        while (v0 >= F->nVars()) F->newVar();
        lits.push(mkLit(v0, lit < 0));
    }
    if (wopt.has_value()) {
        if (*wopt <= 0) throw std::invalid_argument("Soft weight must be positive");
        F->addSoftClause(static_cast<uint64_t>(*wopt), lits);
    } else {
        F->addHardClause(lits);
    }
}

static inline std::vector<ClauseRec> normalize_units_by_literal_lastwins(const std::vector<ClauseRec>& clauses) {
    std::vector<ClauseRec> out;
    std::unordered_map<int, long long> unit_last;
    out.reserve(clauses.size());
    for (const auto& cr : clauses) {
        const auto& cl = cr.first;
        const auto& w = cr.second;
        if (!w.has_value()) {
            out.push_back(cr);
        } else if (cl.size() == 1) {
            unit_last[cl[0]] = *w;
        } else {
            out.push_back(cr);
        }
    }
    for (const auto& kv : unit_last) {
        out.emplace_back(std::vector<int>{kv.first}, WeightOpt(kv.second));
    }
    return out;
}

static inline uint64_t sum_soft_weights(const std::vector<ClauseRec>& cls) {
    uint64_t s = 0;
    for (const auto& cr : cls) if (cr.second.has_value()) s += static_cast<uint64_t>(*cr.second);
    return s;
}

static inline bool any_weight_not_one(const std::vector<ClauseRec>& cls) {
    for (const auto& cr : cls) {
        if (cr.second.has_value() && *cr.second != 1) return true;
    }
    return false;
}

static inline void set_problem_type_and_top(MaxSATFormula* F, const std::vector<ClauseRec>& norm) {
    if (any_weight_not_one(norm)) {
        F->setProblemType(_WEIGHTED_);
    } else {
        F->setProblemType(_UNWEIGHTED_);
    }
    uint64_t top = sum_soft_weights(norm) + 1;
    if (top == 0) top = 1;
    F->setHardWeight(top);
}

static inline void build_formula(MaxSATFormula* F,
                                 const std::vector<ClauseRec>& norm,
                                 int n_vars_ext,
                                 const std::vector<int>* assumptions_opt) {
    for (int i = 0; i < n_vars_ext; ++i) F->newVar();

    std::vector<ClauseRec> hards, soft_nonunits, soft_units;
    hards.reserve(norm.size());
    soft_nonunits.reserve(norm.size());
    soft_units.reserve(norm.size());

    for (const auto& cr : norm) {
        if (!cr.second.has_value()) hards.push_back(cr);
        else if (cr.first.size() == 1) soft_units.push_back(cr);
        else soft_nonunits.push_back(cr);
    }

    for (const auto& cr : hards) append_clause(F, cr.first, cr.second);
    for (const auto& cr : soft_nonunits) append_clause(F, cr.first, cr.second);
    for (const auto& cr : soft_units) append_clause(F, cr.first, cr.second);

    if (assumptions_opt) {
        for (int a : *assumptions_opt) {
            if (a == 0) throw std::invalid_argument("Assumption literal 0 is invalid");
            append_clause(F, std::vector<int>{a}, WeightOpt());
        }
    }

    set_problem_type_and_top(F, norm);
}

class BLSEx : public BLS {
public:
    BLSEx(int verb = 0, int card = _CARD_MTOTALIZER_, int limit = 100000, int mcs = 50, bool local = false)
        : BLS(verb, card, limit, mcs, local) {}

    bool hasModelEx() const { return model.size() != 0; }

    std::vector<int> getModelEx() const {
        std::vector<int> out;
        out.reserve(static_cast<size_t>(model.size()));
        for (int i = 0; i < model.size(); ++i) {
            out.push_back(model[i] == l_True ? (i + 1) : -(i + 1));
        }
        return out;
    }

    bool getValueEx(int var_ext) const {
        if (var_ext <= 0) throw std::invalid_argument("Variable id must be >= 1");
        int idx = var_ext - 1;
        if (idx >= model.size()) return false;
        return model[idx] == l_True;
    }

    uint64_t getCostEx() { return getCost(); }
};

class SPBMaxSATCFPSWrapper {
public:
    SPBMaxSATCFPSWrapper() : n_vars_ext_(0) {}

    int newVar() { return ++n_vars_ext_; }

    void setNInputVars(unsigned int n) {
        if (static_cast<int>(n) > n_vars_ext_) n_vars_ext_ = static_cast<int>(n);
    }

    void addClause(const std::vector<int>& clause_ext, py::object weight_obj = py::none()) {
        int maxv = n_vars_ext_;
        for (int lit : clause_ext) {
            if (lit == 0) throw std::invalid_argument("Literal 0 is invalid");
            maxv = std::max(maxv, std::abs(lit));
        }
        n_vars_ext_ = maxv;

        if (weight_obj.is_none()) {
            clauses_.push_back({clause_ext, WeightOpt()});
        } else {
            long long w = weight_obj.cast<long long>();
            if (w <= 0) throw std::invalid_argument("Soft weight must be positive");
            clauses_.push_back({clause_ext, WeightOpt(w)});
        }
    }

    bool solve(py::object assumptions = py::none()) {
        std::vector<int> assumps;
        if (!assumptions.is_none()) assumps = assumptions.cast<std::vector<int>>();

        auto norm = normalize_units_by_literal_lastwins(clauses_);

        std::unique_ptr<MaxSATFormula> F(new MaxSATFormula());
        build_formula(F.get(), norm, n_vars_ext_, assumptions.is_none() ? nullptr : &assumps);

        solver_.reset(new BLSEx(/*verbosity=*/0, /*card=*/_CARD_MTOTALIZER_, /*limit=*/100000, /*mcs=*/50, /*local=*/false));
        MaxSATFormula* rawF = F.release();
        solver_->loadFormula(rawF);

        solver_->search();  // patched source returns instead of exit()
        return solver_->hasModelEx();
    }

    uint64_t getCost() { return solver_ ? solver_->getCostEx() : 0; }

    bool getValue(int var_ext) const {
        if (!solver_) return false;
        return solver_->getValueEx(var_ext);
    }

    std::vector<int> getModel() const {
        if (!solver_) return {};
        return solver_->getModelEx();
    }

private:
    int n_vars_ext_;
    std::vector<ClauseRec> clauses_;
    std::unique_ptr<BLSEx> solver_;
};

PYBIND11_MODULE(spb_maxsat_c_fps, m) {
    m.doc() = "pybind11 bindings for SPB-MaxSAT-c-FPS (NuWLS-c / BLS path)";

    py::class_<SPBMaxSATCFPSWrapper>(m, "SPBMaxSATCFPS")
        .def(py::init<>())
        .def("newVar", &SPBMaxSATCFPSWrapper::newVar)
        .def("setNInputVars", &SPBMaxSATCFPSWrapper::setNInputVars)
        .def("addClause", &SPBMaxSATCFPSWrapper::addClause, py::arg("clause"), py::arg("weight") = py::none())
        .def("solve", &SPBMaxSATCFPSWrapper::solve, py::arg("assumptions") = py::none())
        .def("getCost", &SPBMaxSATCFPSWrapper::getCost)
        .def("getValue", &SPBMaxSATCFPSWrapper::getValue)
        .def("getModel", &SPBMaxSATCFPSWrapper::getModel);
}
