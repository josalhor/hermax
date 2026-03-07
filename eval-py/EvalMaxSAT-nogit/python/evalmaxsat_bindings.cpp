#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
#include <optional>
#include <unordered_map>
#include <memory>
#include <cmath>
#include <algorithm>

#include "EvalMaxSAT.h"
#include "cadicalinterface.h"

namespace py = pybind11;

class EvalMaxSATWrapper {
    using SolverT = Solver_cadical;
    using EvalT   = EvalMaxSAT<SolverT>;

    // Base solver (persistent)
    std::unique_ptr<EvalT> base_;

    // Temporary solver with assumptions for the last solve
    std::unique_ptr<EvalT> last_with_assum_;

    // Mapping external -> internal variable ids
    std::unordered_map<int, int> ext2int_;
    int n_ext_vars_ = 0;
    unsigned n_int_vars_ = 0;

    // Record of all clauses added to base (in internal var space)
    std::vector<std::pair<std::vector<int>, std::optional<long long>>> history_;
    std::unordered_map<int, uint64_t> soft_lits_; // key = normalized external literal: -var means "[-var]" soft-literal
    // Merge unit softs by literal (signed), last-wins
    std::unordered_map<int, long long> soft_units_last_;
    bool base_dirty_ = false;



    // External assumptions to be injected at next solve
    std::vector<int> pending_assum_;

    // Ensure a literal is declared and mapped
    int map_lit(int lit) {
        int v = std::abs(lit);
        if (v == 0) return 0;
        auto it = ext2int_.find(v);
        if (it == ext2int_.end()) {
            int internal = base_->newVar(true);
            ext2int_[v] = internal;
            n_ext_vars_ = std::max(n_ext_vars_, v);
            n_int_vars_ = std::max(n_int_vars_, static_cast<unsigned>(internal));
            return lit > 0 ? internal : -internal;
        }
        int internal = it->second;
        return lit > 0 ? internal : -internal;
    }

    std::vector<int> map_clause(const std::vector<int>& clause) {
        std::vector<int> out;
        out.reserve(clause.size());
        for (int lit : clause) {
            if (lit != 0)
                out.push_back(map_lit(lit));
        }
        return out;
    }

public:
    EvalMaxSATWrapper() : base_(std::make_unique<EvalT>()) {}

    int newVar(bool decisionVar = true) {
        int ext = ++n_ext_vars_;
        int internal = base_->newVar(decisionVar);
        ext2int_[ext] = internal;
        n_int_vars_ = std::max(n_int_vars_, static_cast<unsigned>(internal));
        return ext;
    }

   int addClause(const std::vector<int>& clause_ext,
              std::optional<long long> weight_opt = std::nullopt) {
        auto clause_int = map_clause(clause_ext);

        // Unit soft clause -> cache by literal, last-wins
        if (weight_opt && clause_int.size() == 1) {
            const int lit_int = clause_int[0];                 // signed literal
            const long long w = *weight_opt;
            if (w <= 0) return 0;                              // ignore nonpositive defensively

            auto it = soft_units_last_.find(lit_int);
            if (it == soft_units_last_.end()) {
                soft_units_last_[lit_int] = w;
                base_dirty_ = true;
            } else if (it->second != w) {
                it->second = w;                                // overwrite semantics
                base_dirty_ = true;
            }
            // Do NOT record unit softs in history_. They’re replayed from cache.
            n_int_vars_ = std::max(n_int_vars_, (unsigned)std::abs(lit_int));
            return 0;
        }

        // Hard or non-unit soft: pass through and record in history_
        int ret_internal = base_->addClause(clause_int, weight_opt);
        history_.emplace_back(clause_int, weight_opt);
        if (ret_internal <= 0) return 0;

        int new_ext = ++n_ext_vars_;
        ext2int_[new_ext] = ret_internal;
        n_int_vars_ = std::max(n_int_vars_, (unsigned)ret_internal);
        return new_ext;
    }


    void rebuild_base_if_dirty() {
        if (!base_dirty_) return;

        auto fresh = std::make_unique<EvalT>();
        for (unsigned i = 0; i < n_int_vars_; ++i) fresh->newVar();

        // Replay hard + non-unit softs
        for (const auto& entry : history_) fresh->addClause(entry.first, entry.second);

        // Materialize unit softs exactly once (idempotent + last-wins)
        // IMPORTANT: use addClause({lit}, w) so core routes to addWeight
        for (const auto& kv : soft_units_last_) {
            const int lit = kv.first;
            const long long w = kv.second;
            if (w <= 0) continue;
            fresh->addClause(std::vector<int>{lit}, w);
        }

        base_ = std::move(fresh);
        base_dirty_ = false;
    }


    void addSoftLit(int lit_ext, uint64_t w) {
        addClause({lit_ext}, static_cast<long long>(w));
    }

    void assume(const std::vector<int>& assumps_ext) {
        for (int lit : assumps_ext) {
            if (lit != 0)
                pending_assum_.push_back(lit);
        }
    }

  // Return 30 (SAT/OPT), 20 (UNSAT)
    // int solve() {
    //     last_with_assum_.reset();

    //     rebuild_base_if_dirty();

    //     if (pending_assum_.empty()) {
    //         bool sat = base_->solve();
    //         return sat ? 30 : 20;
    //     }

    //     auto with = std::make_unique<EvalT>();
    //     for (unsigned i = 0; i < n_int_vars_; ++i) with->newVar();

    //     for (const auto& entry : history_) with->addClause(entry.first, entry.second);
    //     for (const auto& kv : soft_units_last_) {
    //         const int lit = kv.first;
    //         const long long w = kv.second;
    //         if (w <= 0) continue;
    //         with->addClause(std::vector<int>{lit}, w);
    //     }
    //     for (int lit_ext : pending_assum_) {
    //         if (lit_ext == 0) continue;
    //         int lit_int = map_lit(lit_ext);
    //         with->addClause({lit_int}, std::nullopt);  // hard unit
    //     }
    //     pending_assum_.clear();

    //     last_with_assum_ = std::move(with);
    //     bool sat = last_with_assum_->solve();
    //     return sat ? 30 : 20;
    // }

    // Return 30 (SAT/OPT), 20 (UNSAT)
    int solve() {
        last_with_assum_.reset();

        // Always rebuild a fresh solver for solving (even without assumptions).
        // Keep base_ only for variable id mapping and n_int_vars_ tracking.
        auto with = std::make_unique<EvalT>();

        // Pre-size variables
        for (unsigned i = 0; i < n_int_vars_; ++i)
            with->newVar();

        // Replay all hard and non-unit soft clauses exactly as recorded
        for (const auto& entry : history_) {
            with->addClause(entry.first, entry.second);
        }

        // Materialize cached unit softs (merge-by-literal, last-wins).
        // Use addClause({lit}, w) so the core routes to addWeight and
        // applies its internal merging and bookkeeping correctly.
        for (const auto& kv : soft_units_last_) {
            const int lit = kv.first;           // signed literal
            const long long w = kv.second;
            if (w <= 0) continue;
            with->addClause(std::vector<int>{lit}, w);
        }

        // Inject assumptions as hard units (if any)
        if (!pending_assum_.empty()) {
            for (int lit_ext : pending_assum_) {
                if (lit_ext == 0) continue;
                int lit_int = map_lit(lit_ext);            // uses base_ only for mapping/newVar
                with->addClause({lit_int}, std::nullopt);  // hard unit
            }
            pending_assum_.clear();
        }

        last_with_assum_ = std::move(with);
        bool sat = last_with_assum_->solve();
        return sat ? 30 : 20;
    }


    uint64_t getCost() const {
        if (last_with_assum_)
            return static_cast<uint64_t>(last_with_assum_->getCost());
        return static_cast<uint64_t>(base_->getCost());
    }

    py::object getValue(int lit_ext) {
        if (lit_ext == 0)
            return py::none();
        int v = std::abs(lit_ext);
        auto it = ext2int_.find(v);
        if (it == ext2int_.end())
            return py::none();

        EvalT* src = last_with_assum_ ? last_with_assum_.get() : base_.get();
        int lit_int = lit_ext > 0 ? it->second : -it->second;
        bool val = src->getValue(lit_int);
        return py::cast(val);
    }

    // Pass-through config
    void set_coef(double a, double b) { base_->setCoef(a, b); }
    void set_target_computation_time(double t) { base_->setTargetComputationTime(t); }
    void set_bound_ref_time(double a, double b) { base_->setBoundRefTime(a, b); }
    void unactivate_delay_strategy() { base_->unactivateDelayStrategy(); }
    void unactivate_multisolve_strategy() { base_->unactivateMultiSolveStrategy(); }
    void unactivate_ub_strategy() { base_->unactivateUBStrategy(); }
    void disable_optimize() { base_->disableOptimize(); }
    void set_incremental(bool v = true) { base_->setIncremental(v); }

    unsigned nVars() const { return base_->nVars(); }
    void set_n_input_vars(unsigned n) { base_->setNInputVars(n); }

    std::vector<bool> getSolution() {
        EvalT* src = last_with_assum_ ? last_with_assum_.get() : base_.get();
        return src->getSolution();
    }

    void set_terminate(std::optional<std::function<int()>>) {
        throw std::runtime_error("set_terminate is not supported by EvalMaxSAT; no solver hook exists.");
    }

    const char* signature() const { return "EvalMaxSAT<cadical>"; }
};

PYBIND11_MODULE(eval_py, m) {
    m.doc() = "pybind11 plugin for EvalMaxSAT with UWr-like interface";

    py::class_<EvalMaxSATWrapper>(m, "EvalMaxSAT")
        .def(py::init<>())

        // Core interface
        .def("newVar", &EvalMaxSATWrapper::newVar, py::arg("decisionVar") = true)
        .def("addClause", &EvalMaxSATWrapper::addClause,
             py::arg("clause"), py::arg("weight") = std::nullopt,
             "Add a clause. If weight is None, it's hard. Returns soft aux var ext-id or 0.")
        .def("addSoftLit", &EvalMaxSATWrapper::addSoftLit, py::arg("lit"), py::arg("weight"))
        .def("assume", &EvalMaxSATWrapper::assume, py::arg("assumptions"))
        .def("solve", &EvalMaxSATWrapper::solve)
        .def("getCost", &EvalMaxSATWrapper::getCost)
        .def("getValue", &EvalMaxSATWrapper::getValue, py::arg("lit"))

        // Configuration passthroughs
        .def("set_coef", &EvalMaxSATWrapper::set_coef, py::arg("initial_coef"), py::arg("coef_on_ref_time"))
        .def("set_target_computation_time", &EvalMaxSATWrapper::set_target_computation_time, py::arg("target_time_sec"))
        .def("set_bound_ref_time", &EvalMaxSATWrapper::set_bound_ref_time, py::arg("minimal_ref_time"), py::arg("maximal_ref_time"))
        .def("unactivate_delay_strategy", &EvalMaxSATWrapper::unactivate_delay_strategy)
        .def("unactivate_multisolve_strategy", &EvalMaxSATWrapper::unactivate_multisolve_strategy)
        .def("unactivate_ub_strategy", &EvalMaxSATWrapper::unactivate_ub_strategy)
        .def("disable_optimize", &EvalMaxSATWrapper::disable_optimize)
        .def("set_incremental", &EvalMaxSATWrapper::set_incremental, py::arg("value") = true)

        // Solution access
        .def("nVars", &EvalMaxSATWrapper::nVars)
        .def("set_n_input_vars", &EvalMaxSATWrapper::set_n_input_vars, py::arg("n"))
        .def("getSolution", &EvalMaxSATWrapper::getSolution)

        // Parity stubs
        .def("set_terminate", &EvalMaxSATWrapper::set_terminate, py::arg("callback") = std::nullopt)
        .def("signature", &EvalMaxSATWrapper::signature);
}
