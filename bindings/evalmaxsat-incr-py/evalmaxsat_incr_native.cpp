#include "evalmaxsat_incr_native.h"
#include "../../solvers/EvalMaxSAT2022/ipamir.h"
#include <limits>
#include <stdexcept>

namespace evalmaxsat_incr_native {
static void validate_literal(int lit) {
    if (lit == 0 || lit == std::numeric_limits<int>::min())
        throw std::invalid_argument("literal must be nonzero and safely negatable");
}
Solver::Solver() : solver_(ipamir_init()) {
    if (!solver_)
        throw std::runtime_error("Failed to initialize EvalMaxSATIncr solver.");
}
Solver::~Solver() {
    if (solver_) {
        ipamir_release(solver_);
        solver_ = nullptr;
    }
}
void Solver::add_clause(const std::vector<int> &clause, std::optional<long long> weight) {
    for (int lit : clause)
        validate_literal(lit);
    if (!weight) {
        for (int lit : clause)
            ipamir_add_hard(solver_, lit);
        ipamir_add_hard(solver_, 0);
    } else if (clause.size() == 1) {
        ipamir_add_soft_lit(solver_, -clause[0], static_cast<uint64_t>(*weight));
    } else {
        throw std::runtime_error("EvalMaxSATIncr (IPAMIR) only supports unit soft clauses "
                                 "directly. Use add_soft_relaxed logic in Python.");
    }
}
void Solver::add_soft_lit(int lit, uint64_t weight) {
    validate_literal(lit);
    ipamir_add_soft_lit(solver_, lit, weight);
}
void Solver::assume(const std::vector<int> &assumptions) {
    for (int lit : assumptions)
        validate_literal(lit);
    for (int lit : assumptions)
        ipamir_assume(solver_, lit);
}
int Solver::solve() { return ipamir_solve(solver_); }
uint64_t Solver::get_cost() { return ipamir_val_obj(solver_); }
int Solver::get_value(int lit) {
    validate_literal(lit);
    return ipamir_val_lit(solver_, lit);
}
std::string Solver::signature() {
    const char *value = ipamir_signature();
    return value ? value : "";
}
} // namespace evalmaxsat_incr_native
