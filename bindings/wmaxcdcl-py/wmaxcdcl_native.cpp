#include "wmaxcdcl_native.h"
#include "simp/SimpSolver.h"
#include <climits>
#include <cstdlib>
#include <stdexcept>

namespace wmaxcdcl_native {
class Solver::Impl {
  public:
    Minisat::SimpSolver solver;
    bool prepared = false;
    int n_input_vars = 0;
    Impl() { reset_maxsat_state(); }
    void reset_maxsat_state() {
        solver.parsing = false;
        solver.instanceType = 1;
        solver.hardWeight = INT64_MAX;
        solver.initUB = INT64_MAX;
        solver.initLB = 0;
        solver.UB = INT64_MAX;
        solver.nbOriVars = 0;
        solver.nbOrignalVars = 0;
        prepared = false;
    }
    void ensure_var(int v1) {
        if (v1 <= 0)
            return;
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
        if (grew)
            prepared = false;
    }
};
Solver::Solver() : impl_(new Impl()) {}
Solver::~Solver() = default;
int Solver::new_var(bool decision_var) {
    (void)decision_var;
    int v = impl_->solver.newVar() + 1;
    if (v > impl_->n_input_vars) {
        impl_->n_input_vars = v;
        impl_->solver.nbOriVars = v;
        impl_->solver.nbOrignalVars = v;
    }
    impl_->prepared = false;
    return v;
}
bool Solver::add_clause(const std::vector<int> &clause, bool has_weight, long long weight) {
    for (int lit : clause)
        if (lit == 0 || lit == INT_MIN)
            throw std::invalid_argument("literal must be nonzero and safely negatable");
    if (has_weight && weight <= 0)
        throw std::invalid_argument("weight must be positive");
    if (has_weight && impl_->solver.totalWeight > INT64_MAX - weight)
        throw std::overflow_error("sum of soft weights exceeds INT64_MAX");
    Minisat::vec<Minisat::Lit> ps;
    ps.clear();
    for (int lit : clause) {
        impl_->ensure_var(std::abs(lit));
        ps.push(Minisat::mkLit(std::abs(lit) - 1, lit < 0));
    }
    impl_->prepared = false;
    if (has_weight) {
        bool ok = impl_->solver.addClause_(ps, static_cast<int64_t>(weight));
        if (ok)
            impl_->solver.totalWeight += static_cast<int64_t>(weight);
        return ok;
    }
    return impl_->solver.addClause_(ps, 0);
}
void Solver::set_n_input_vars(unsigned int n) {
    if (n > static_cast<unsigned int>(INT_MAX))
        throw std::overflow_error("n exceeds supported variable range");
    impl_->ensure_var(static_cast<int>(n));
    impl_->n_input_vars = static_cast<int>(n);
    impl_->solver.nbOriVars = static_cast<int>(n);
    impl_->solver.nbOrignalVars = static_cast<int>(n);
}
void Solver::prepare() {
    if (impl_->prepared)
        return;
    if (impl_->solver.totalWeight >= 0 && impl_->solver.totalWeight < (INT64_MAX - 1)) {
        impl_->solver.hardWeight = impl_->solver.totalWeight + 1;
        impl_->solver.UB = impl_->solver.hardWeight;
    }
    impl_->solver.parsing = false;
    impl_->solver.nbOriVars = impl_->n_input_vars;
    impl_->solver.nbOrignalVars = impl_->n_input_vars;
    impl_->prepared = true;
}
bool Solver::solve(const std::vector<int> &assumptions, bool) {
    Minisat::vec<Minisat::Lit> assumps;
    for (int lit : assumptions) {
        if (lit == 0 || lit == INT_MIN)
            throw std::invalid_argument("assumption literal must be nonzero and safely negatable");
    }
    for (int lit : assumptions) {
        impl_->ensure_var(std::abs(lit));
        assumps.push(Minisat::mkLit(std::abs(lit) - 1, lit < 0));
    }
    prepare();
    return impl_->solver.solve(assumps, true, false);
}
long long Solver::get_cost() const { return static_cast<long long>(impl_->solver.optimal); }
bool Solver::get_value(int lit) const {
    if (lit == 0 || lit == INT_MIN)
        throw std::invalid_argument("literal must be nonzero and safely negatable");
    int v = std::abs(lit) - 1;
    if (v < 0 || v >= impl_->solver.model.size())
        return false;
    bool val = impl_->solver.model[v] == l_True;
    return lit > 0 ? val : !val;
}
std::vector<int> Solver::get_model() const {
    std::vector<int> model;
    int n =
        impl_->solver.nbOrignalVars > 0 ? impl_->solver.nbOrignalVars : impl_->solver.model.size();
    model.reserve(static_cast<size_t>(n));
    for (int i = 0; i < n; ++i)
        model.push_back(
            i < impl_->solver.model.size() && impl_->solver.model[i] == l_True ? i + 1 : -(i + 1));
    return model;
}
} // namespace wmaxcdcl_native
