// openwbo_bindings.cpp
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "algorithms/Alg_OLL.h"
#include "algorithms/Alg_PartMSU3.h"
#include "algorithms/Alg_MSU3.h"
#include "MaxSATFormula.h"

#include <unordered_map>
#include <vector>
#include <memory>
#include <algorithm>
#include <stdexcept>
#include <cstdlib>

namespace py = pybind11;
using namespace openwbo;

// C++14 replacement for std::optional<long long>
struct WeightOpt {
    bool has_val;
    long long val;

    WeightOpt() : has_val(false), val(0) {}
    WeightOpt(long long v) : has_val(true), val(v) {}

    bool has_value() const { return has_val; }
    long long value() const { return val; }
    long long operator*() const { return val; }
};

// Store as (clause, optional weight). If weight has value => soft; else => hard.
using ClauseRec = std::pair<std::vector<int>, WeightOpt>;

// ---------- helpers ----------

static inline void append_clause(MaxSATFormula* F,
                                 const std::vector<int>& clause_ext,
                                 const WeightOpt& wopt)
{
    vec<Lit> lits;
    lits.capacity(clause_ext.size());
    for (int lit : clause_ext) {
        if (lit == 0) throw std::invalid_argument("Literal 0 is invalid");
        const int v0 = std::abs(lit) - 1;      // Minisat/Open-WBO are 0-based
        while (v0 >= F->nVars()) F->newVar();
        lits.push(mkLit(v0, lit < 0));         // mkLit(var0, sign=true means NEGATED)
    }
    if (wopt.has_value()) {
        if (*wopt <= 0) throw std::invalid_argument("Soft weight must be positive");
        F->addSoftClause(*wopt, lits);
    } else {
        F->addHardClause(lits);
    }
}

static inline std::vector<ClauseRec>
normalize_units_by_literal_lastwins(const std::vector<ClauseRec>& clauses)
{
    std::vector<ClauseRec> out_nonunits_and_hards;
    std::unordered_map<int, long long> last_unit_w; // literal -> weight (last-wins)

    for (const auto& cr : clauses) {
        const auto& cl   = cr.first;
        const auto& wopt = cr.second;
        if (!wopt.has_value()) {
            out_nonunits_and_hards.push_back(cr);              // hard
        } else if (cl.size() == 1) {
            last_unit_w[cl[0]] = *wopt;                        // soft unit (merge by literal)
        } else {
            out_nonunits_and_hards.push_back(cr);              // soft non-unit (multiset)
        }
    }
    // append merged soft units
    for (const auto& kv : last_unit_w) {
        out_nonunits_and_hards.emplace_back(
            std::vector<int>{kv.first},
            WeightOpt(kv.second)
        );
    }
    return out_nonunits_and_hards;
}

static inline uint64_t sum_soft_weights(const std::vector<ClauseRec>& cls) {
    uint64_t s = 0;
    for (const auto& cr : cls) if (cr.second.has_value()) s += (uint64_t)*cr.second;
    return s;
}
static inline uint64_t count_soft(const std::vector<ClauseRec>& cls) {
    uint64_t c = 0;
    for (const auto& cr : cls) if (cr.second.has_value()) ++c;
    return c;
}

static inline bool any_weight_not_one(const std::vector<ClauseRec>& cls) {
    for (const auto& cr : cls)
        if (cr.second.has_value() && *cr.second != 1) return true;
    return false;
}

static inline void set_problem_type_and_top(MaxSATFormula* F,
                                            const std::vector<ClauseRec>& all_norm) {
    if (any_weight_not_one(all_norm)) {
        F->setProblemType(_WEIGHTED_);
        uint64_t top = sum_soft_weights(all_norm) + 1;
        if (top == 0) top = 1;
        F->setHardWeight(top);
    } else {
        F->setProblemType(_UNWEIGHTED_);
        uint64_t top = count_soft(all_norm) + 1;
        if (top == 0) top = 1;
        F->setHardWeight(top);
    }
}

// Build formula F from normalized clauses and optional assumptions.
// Replay order: hards → soft non-units → soft units, then inject assumptions as hard units.
// n_vars_ext = max external var index (1-based).
static inline void build_formula(MaxSATFormula* F,
                                 const std::vector<ClauseRec>& norm,
                                 int n_vars_ext,
                                 const std::vector<int>* assumptions_opt)
{
    for (int i = 0; i < n_vars_ext; ++i) F->newVar();

    std::vector<ClauseRec> hards, soft_nonunits, soft_units;
    hards.reserve(norm.size()); soft_nonunits.reserve(norm.size()); soft_units.reserve(norm.size());

    for (const auto& cr : norm) {
        const auto& cl = cr.first;
        const auto& w  = cr.second;
        if (!w.has_value())               hards.push_back(cr);
        else if (cl.size() == 1)          soft_units.push_back(cr);
        else                              soft_nonunits.push_back(cr);
    }

    for (const auto& cr : hards)         append_clause(F, cr.first, cr.second);
    for (const auto& cr : soft_nonunits) append_clause(F, cr.first, cr.second);
    for (const auto& cr : soft_units)    append_clause(F, cr.first, cr.second);

    if (assumptions_opt) {
        for (int a : *assumptions_opt) {
            if (a == 0) throw std::invalid_argument("Assumption literal 0 is invalid");
            append_clause(F, std::vector<int>{a}, WeightOpt()); // hard unit
        }
    }

    set_problem_type_and_top(F, norm);
}

// ---------- OLL wrapper (rebuild-on-solve) ----------

class OLLWrapper {
public:
    OLLWrapper() : n_vars_ext_(0) {}

    int newVar() { return ++n_vars_ext_; }

    void addClause(const std::vector<int>& clause_ext, py::object weight_obj) {
        int maxv = n_vars_ext_;
        for (int lit : clause_ext) {
            if (lit == 0) throw std::invalid_argument("Literal 0 is invalid");
            maxv = std::max(maxv, std::abs(lit));
        }
        n_vars_ext_ = maxv;

        if (weight_obj.is_none()) {
            clauses_.push_back({clause_ext, WeightOpt()});              // hard
        } else {
            long long w = weight_obj.cast<long long>();
            if (w <= 0) throw std::invalid_argument("Soft weight must be positive");
            clauses_.push_back({clause_ext, WeightOpt(w)}); // soft
        }
    }

    bool solve(py::object assumptions = py::none()) {
        std::vector<int> assumps;
        if (!assumptions.is_none()) {
            assumps = assumptions.cast<std::vector<int>>();
        }
        auto norm = normalize_units_by_literal_lastwins(clauses_);

        std::unique_ptr<MaxSATFormula> F(new MaxSATFormula());
        build_formula(F.get(), norm, n_vars_ext_, assumptions.is_none() ? nullptr : &assumps);

        solver_.reset(new OLL(/*verbosity=*/0, /*cardinality=*/1));
        MaxSATFormula* rawF = F.release();
        solver_->loadFormula(rawF);

        StatusCode st = solver_->search();
        return st == _OPTIMUM_ || st == _SATISFIABLE_;
    }

    uint64_t getCost() const { return solver_ ? solver_->getCost() : 0; }
    bool getValue(int var_ext) const {
        if (!solver_ || var_ext <= 0 || var_ext > n_vars_ext_) return false;
        return solver_->getValue(var_ext - 1) > 0;
    }

private:
    int n_vars_ext_;
    std::vector<ClauseRec> clauses_;
    std::unique_ptr<MaxSAT> solver_;
};

// ---------- PartMSU3 wrapper (rebuild-on-solve + fallback to MSU3) ----------

class PartMSU3Wrapper {
public:
    PartMSU3Wrapper() : n_vars_ext_(0) {}

    int newVar() { return ++n_vars_ext_; }

    void addClause(const std::vector<int>& clause_ext, py::object weight_obj) {
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
            if (w != 1) throw py::value_error("PartMSU3 only supports soft weight == 1.");
            clauses_.push_back({clause_ext, WeightOpt(w)});
        }
    }

    bool solve(py::object assumptions = py::none()) {
        std::vector<int> assumps;
        if (!assumptions.is_none()) assumps = assumptions.cast<std::vector<int>>();
        auto norm = normalize_units_by_literal_lastwins(clauses_);

        std::unique_ptr<MaxSATFormula> F(new MaxSATFormula());
        build_formula(F.get(), norm, n_vars_ext_, assumptions.is_none() ? nullptr : &assumps);

        std::unique_ptr<PartMSU3> pmsu(new PartMSU3(/*verbosity=*/0, /*partition_strategy=*/2,
                                                    /*graph_type=*/2, /*cardinality=*/1));
        MaxSATFormula* rawF = F.release();
        pmsu->loadFormula(rawF);

        // choose/fallback
        int algo_id = pmsu->chooseAlgorithm();
        if (algo_id == 2) {
            MaxSATFormula* reclaimed = pmsu->releaseFormula();
            pmsu.reset();
            // Fallback: plain MSU3
            std::unique_ptr<MSU3> msu(new MSU3(/*verbosity=*/0));
            msu->loadFormula(reclaimed);
            solver_ = std::move(msu);
        } else {
            solver_ = std::move(pmsu);
        }

        StatusCode st = solver_->search();
        return st == _OPTIMUM_ || st == _SATISFIABLE_;
    }

    uint64_t getCost() const { return solver_ ? solver_->getCost() : 0; }
    bool getValue(int var_ext) const {
        if (!solver_ || var_ext <= 0 || var_ext > n_vars_ext_) return false;
        return solver_->getValue(var_ext - 1) > 0;
    }

private:
    int n_vars_ext_;
    std::vector<ClauseRec> clauses_;
    std::unique_ptr<MaxSAT> solver_; // PartMSU3 or MSU3 after chooseAlgorithm()
};

// ---------- Auto wrapper (pick OLL vs PartMSU3/MSU3) ----------

class OpenWBOAutoWrapper {
public:
    OpenWBOAutoWrapper() : n_vars_ext_(0) {}

    int newVar() { return ++n_vars_ext_; }

    void addClause(const std::vector<int>& clause_ext, py::object weight_obj) {
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

        // Decide engine: weighted → OLL; else PartMSU3 with fallback to MSU3
        if (any_weight_not_one(norm)) {
            std::unique_ptr<OLL> oll(new OLL(/*verbosity=*/0, /*cardinality=*/1));
            MaxSATFormula* rawF = F.release();
            oll->loadFormula(rawF);
            solver_ = std::move(oll);
        } else {
            std::unique_ptr<PartMSU3> pmsu(new PartMSU3(/*verbosity=*/0, /*partition_strategy=*/2,
                                                        /*graph_type=*/2, /*cardinality=*/1));
            MaxSATFormula* rawF = F.release();
            pmsu->loadFormula(rawF);
            int algo_id = pmsu->chooseAlgorithm();
            if (algo_id == 2) {
                MaxSATFormula* reclaimed = pmsu->releaseFormula();
                pmsu.reset();
                std::unique_ptr<MSU3> msu(new MSU3(/*verbosity=*/0));
                msu->loadFormula(reclaimed);
                solver_ = std::move(msu);
            } else {
                solver_ = std::move(pmsu);
            }
        }

        StatusCode st = solver_->search();
        return st == _OPTIMUM_ || st == _SATISFIABLE_;
    }

    uint64_t getCost() const { return solver_ ? solver_->getCost() : 0; }
    bool getValue(int var_ext) const {
        if (!solver_ || var_ext <= 0 || var_ext > n_vars_ext_) return false;
        return solver_->getValue(var_ext - 1) > 0;
    }

private:
    int n_vars_ext_;
    std::vector<ClauseRec> clauses_;
    std::unique_ptr<MaxSAT> solver_;
};

// ---------- module ----------

PYBIND11_MODULE(openwbo, m) {
    m.doc() = "Open-WBO (OLL, PartMSU3/MSU3, Auto) — rebuild-on-solve + unit-by-literal last-wins + assumptions";

    py::class_<OLLWrapper>(m, "OLL")
        .def(py::init<>())
        .def("newVar", &OLLWrapper::newVar)
        .def("addClause", &OLLWrapper::addClause, py::arg("clause"), py::arg("weight") = py::none())
        .def("solve", &OLLWrapper::solve, py::arg("assumptions") = py::none())
        .def("getCost", &OLLWrapper::getCost)
        .def("getValue", &OLLWrapper::getValue);

    py::class_<PartMSU3Wrapper>(m, "PartMSU3")
        .def(py::init<>())
        .def("newVar", &PartMSU3Wrapper::newVar)
        .def("addClause", &PartMSU3Wrapper::addClause, py::arg("clause"), py::arg("weight") = py::none())
        .def("solve", &PartMSU3Wrapper::solve, py::arg("assumptions") = py::none())
        .def("getCost", &PartMSU3Wrapper::getCost)
        .def("getValue", &PartMSU3Wrapper::getValue);

    py::class_<OpenWBOAutoWrapper>(m, "Auto")
        .def(py::init<>())
        .def("newVar", &OpenWBOAutoWrapper::newVar)
        .def("addClause", &OpenWBOAutoWrapper::addClause, py::arg("clause"), py::arg("weight") = py::none())
        .def("solve", &OpenWBOAutoWrapper::solve, py::arg("assumptions") = py::none())
        .def("getCost", &OpenWBOAutoWrapper::getCost)
        .def("getValue", &OpenWBOAutoWrapper::getValue);
}