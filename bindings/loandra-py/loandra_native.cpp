#include "loandra_native.h"
#include "algorithms/Alg_OLL.h"
#include "MaxSATFormula.h"
#include <cstdlib>
#include <stdexcept>

namespace loandra_native {
using namespace openwbo;
class OLLEx : public OLL {
  public:
    OLLEx(int verbosity, int cardinality) : OLL(verbosity, cardinality) {}
    bool has_model() const { return model.size() != 0; }
    bool get_value(int var) const {
        if (var <= 0)
            throw std::invalid_argument("Variable id must be >= 1");
        int idx = var - 1;
        if (idx >= static_cast<int>(model.size()))
            return false;
        return model[idx] == l_True;
    }
    std::vector<int> get_model() const {
        std::vector<int> out;
        out.reserve(model.size());
        for (int i = 0; i < static_cast<int>(model.size()); ++i)
            out.push_back(model[i] == l_True ? i + 1 : -(i + 1));
        return out;
    }
};
class Solver::Impl {
  public:
    MaxSATFormula *formula = new MaxSATFormula();
    OLLEx *solver = new OLLEx(0, 1);
    bool transferred = false;
    ~Impl() {
        if (!transferred && formula)
            delete formula;
        delete solver;
    }
};
Solver::Solver() : impl_(new Impl()) {}
Solver::~Solver() = default;
int Solver::new_var() {
    impl_->formula->newVar();
    return impl_->formula->nVars();
}
void Solver::add_clause(const std::vector<int> &clause, bool has_weight, long long weight) {
    if (impl_->transferred)
        throw std::runtime_error("Cannot add clauses after solve");
    for (int lit : clause)
        if (!lit)
            throw std::invalid_argument("Literal 0 is invalid");
    if (has_weight && weight <= 0)
        throw std::invalid_argument("Soft weight must be positive");
    vec<Lit> lits;
    lits.capacity(clause.size());
    for (int lit : clause) {
        int var = std::abs(lit) - 1;
        while (var >= impl_->formula->nVars())
            impl_->formula->newVar();
        lits.push(mkLit(var, lit < 0));
    }
    if (has_weight)
        impl_->formula->addSoftClause(static_cast<uint64_t>(weight), lits);
    else
        impl_->formula->addHardClause(lits);
}
bool Solver::solve() {
    if (!impl_->transferred) {
        impl_->solver->loadFormula(impl_->formula);
        impl_->transferred = true;
    }
    impl_->solver->search();
    return impl_->solver->has_model();
}
uint64_t Solver::get_cost() { return impl_->solver->getUB(); }
bool Solver::get_value(int var) { return impl_->solver->get_value(var); }
std::vector<int> Solver::get_model() const { return impl_->solver->get_model(); }
} // namespace loandra_native
