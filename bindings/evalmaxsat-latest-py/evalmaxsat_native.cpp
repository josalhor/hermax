#include "evalmaxsat_native.h"
#include "EvalMaxSAT.h"
#include <cstdlib>
#include <stdexcept>

namespace evalmaxsat_native {
class Solver::Impl {
  public:
    EvalMaxSAT<Solver_cadical> solver;
    Impl() {
#if defined(__APPLE__)
        solver.disableOptimize();
        solver.disablePreprocessing();
#endif
    }
};

Solver::Solver() : impl_(new Impl()) {}
Solver::~Solver() = default;
int Solver::new_var(bool decision_var) { return impl_->solver.newVar(decision_var); }
int Solver::add_clause(const std::vector<int> &clause, std::optional<long long> weight) {
    for (int lit : clause) {
        if (!lit)
            throw std::invalid_argument("Literal 0 is invalid");
    }
    return impl_->solver.addClause(clause, weight);
}
bool Solver::solve() { return impl_->solver.solve(); }
long long Solver::get_cost() { return static_cast<long long>(impl_->solver.getCost()); }
bool Solver::get_value(int lit) { return impl_->solver.getValue(lit); }
std::vector<int> Solver::get_model() {
    std::vector<int> model;
    int n = impl_->solver.nVars();
    model.reserve(static_cast<size_t>(n));
    for (int i = 1; i <= n; ++i)
        model.push_back(impl_->solver.getValue(i) ? i : -i);
    return model;
}
void Solver::set_n_input_vars(unsigned int n) { impl_->solver.setNInputVars(n); }
} // namespace evalmaxsat_native
