#include "maxhs_native.h"
#include "maxhs/core/MaxSolver.h"
#include "maxhs/core/Wcnf.h"
#include "maxhs/utils/Params.h"
#include <cmath>
#include <cstdlib>
#ifdef GLUCOSE
#include "glucose/utils/Options.h"
namespace Minisat = Glucose;
#else
#include "minisat/utils/Options.h"
#endif
using Minisat::l_True;
using Minisat::Lit;
using Minisat::mkLit;
struct MaxHSWrapperNative::Impl {
    Wcnf *f = nullptr;
    MaxHS::MaxSolver *solver = nullptr;
    int num_vars = 0;
    bool solved = false;
    int last_status = 60;
    Impl() {
        params.readOptions();
        params.mx_find_mxes = 0;
        params.verbosity = 0;
        params.sverbosity = 0;
        params.mverbosity = 0;
        f = new Wcnf();
    }
    ~Impl() {
        delete solver;
        delete f;
    }
};
MaxHSWrapperNative::MaxHSWrapperNative() : impl_(new Impl()) {}
MaxHSWrapperNative::~MaxHSWrapperNative() { delete impl_; }
int MaxHSWrapperNative::newVar() { return ++impl_->num_vars; }
void MaxHSWrapperNative::setNInputVars(int n) {
    if (n > impl_->num_vars)
        impl_->num_vars = n;
}
void MaxHSWrapperNative::addClause(const std::vector<int> &cl, std::optional<long long> w) {
    std::vector<Lit> ls;
    for (int x : cl) {
        int v = std::abs(x);
        if (v > impl_->num_vars)
            impl_->num_vars = v;
        ls.push_back(mkLit(v - 1, x < 0));
    }
    if (w)
        impl_->f->addSoftClause(ls, (Weight)*w);
    else
        impl_->f->addHardClause(ls);
    impl_->solved = false;
}
bool MaxHSWrapperNative::solve() {
    delete impl_->solver;
    impl_->solver = nullptr;
    impl_->f->set_dimacs_params(impl_->num_vars, impl_->f->nHards() + impl_->f->nSofts());
    impl_->solver = new MaxHS::MaxSolver(impl_->f);
    impl_->solver->solve();
    if (impl_->solver->isSolved() && impl_->solver->isUnsat()) {
        impl_->last_status = 20;
        impl_->solved = false;
    } else if (impl_->solver->isSolved() && !impl_->solver->isUnsat()) {
        impl_->last_status = 30;
        impl_->solved = true;
    } else {
        impl_->last_status = 60;
        impl_->solved = false;
    }
    return impl_->solved;
}
int MaxHSWrapperNative::status() const { return impl_->last_status; }
long long MaxHSWrapperNative::cost() {
    return impl_->solver ? (long long)(impl_->solver->UB() + impl_->f->baseCost()) : 0;
}
std::vector<int> MaxHSWrapperNative::model() {
    if (!impl_->solved || !impl_->solver)
        return {};
    const auto &m = impl_->solver->getBestModel();
    std::vector<int> v;
    for (int i = 0; i < impl_->num_vars; ++i)
        v.push_back(i < (int)m.size() && m[i] == l_True ? i + 1 : -(i + 1));
    return v;
}
