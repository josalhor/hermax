#include "openwbo_inc_native.h"
#include "algorithms/Alg_OLL.h"
#include "MaxSATFormula.h"
#include <cstdlib>
#include <stdexcept>
using namespace openwbo;
struct OpenWBOIncNative::Impl {
    MaxSATFormula *formula = new MaxSATFormula();
    MaxSAT *solver = new OLL(-1, 1);
    bool transferred = false;
    ~Impl() {
        if (!transferred)
            delete formula;
        delete solver;
    }
};
OpenWBOIncNative::OpenWBOIncNative() : impl_(new Impl()) {}
OpenWBOIncNative::~OpenWBOIncNative() { delete impl_; }
int OpenWBOIncNative::new_var() {
    impl_->formula->newVar();
    return impl_->formula->nVars();
}
void OpenWBOIncNative::add_clause(const std::vector<int> &clause, bool soft, long long weight) {
    if (impl_->transferred)
        throw std::runtime_error("formula has already been loaded");
    vec<Lit> lits;
    for (int literal : clause) {
        if (!literal)
            throw std::invalid_argument("literal must be nonzero");
        int var = std::abs(literal) - 1;
        while (var >= impl_->formula->nVars())
            impl_->formula->newVar();
        lits.push(mkLit(var, literal < 0));
    }
    if (!soft)
        impl_->formula->addHardClause(lits);
    else {
        if (weight <= 0)
            throw std::invalid_argument("soft weight must be positive");
        impl_->formula->addSoftClause(weight, lits);
    }
}
bool OpenWBOIncNative::solve() {
    if (!impl_->transferred) {
        impl_->solver->loadFormula(impl_->formula);
        impl_->transferred = true;
    }
    impl_->solver->search();
    return impl_->solver->getModel().size() > 0;
}
uint64_t OpenWBOIncNative::cost() const { return impl_->solver->getUB(); }
bool OpenWBOIncNative::value(int var) const {
    if (var > 0 && var <= impl_->formula->nVars())
        return impl_->solver->getModel()[var - 1] == l_True;
    return false;
}
