#include "tt_openwbo_native.h"
#include "../../solvers/tt-open-wbo-inc/code/MaxSATFormulaExtended.h"
#include "../../solvers/tt-open-wbo-inc/code/MaxTypes.h"
#include "../../solvers/tt-open-wbo-inc/code/Torc.h"
#include "../../solvers/tt-open-wbo-inc/code/algorithms/Alg_LinearSU_Clustering.h"
#include "../../solvers/tt-open-wbo-inc/code/algorithms/Alg_OBV.h"
#include <cstdlib>
#include <stdexcept>
using namespace openwbo;
namespace {
class ModelAccessOBV : public OBV {
  public:
    using OBV::OBV;
    vec<lbool> &exposed() { return model; }
};
class ModelAccessLinear : public LinearSUClustering {
  public:
    using LinearSUClustering::LinearSUClustering;
    vec<lbool> &exposed() { return model; }
};
enum class Kind { Obv, Linear };
void apply_defaults(MaxSATFormula *f) {
    Torc::Instance()->SetMsVerbosity(0);
    Torc::Instance()->SetPrintEveryModel(0);
    if (!f)
        return;
    int total = f->nSoft() + f->nHard();
    double fraction = total ? double(f->nSoft()) / double(total) : 0.;
    if (fraction > Torc::Instance()->GetOptimisticMaxSoftFraction())
        Torc::Instance()->SetPolOptimistic(false);
    if (fraction > Torc::Instance()->GetConservativeMaxSoftFraction())
        Torc::Instance()->SetPolConservative(false);
    if (f->getProblemType() == _UNWEIGHTED_) {
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
        Torc::Instance()->toporParams.insert(Torc::Instance()->toporParams.begin(),
                                             std::make_pair("/mode/value", 5.0));
        Torc::Instance()->SetMsModelPerSecThr(.25);
        Torc::Instance()->SetMsPropPerModelThr(100000000);
    }
}
} // namespace
struct TTOpenWBOIncNative::Impl {
    MaxSATFormulaExtended *formula = new MaxSATFormulaExtended();
    MaxSAT *solver = nullptr;
    bool transferred = false;
    Kind kind = Kind::Obv;
    ~Impl() {
        if (!transferred)
            delete formula;
        delete solver;
    }
    vec<lbool> &model() {
        if (kind == Kind::Obv)
            return static_cast<ModelAccessOBV *>(solver)->exposed();
        return static_cast<ModelAccessLinear *>(solver)->exposed();
    }
};
TTOpenWBOIncNative::TTOpenWBOIncNative() : impl_(new Impl()) {}
TTOpenWBOIncNative::~TTOpenWBOIncNative() { delete impl_; }
int TTOpenWBOIncNative::new_var() {
    if (impl_->transferred)
        throw std::runtime_error("formula already loaded");
    impl_->formula->newVar();
    return impl_->formula->nVars();
}
void TTOpenWBOIncNative::add_clause(const std::vector<int> &c, bool soft, long long weight) {
    if (impl_->transferred)
        throw std::runtime_error("formula already loaded");
    vec<Lit> lits;
    for (int x : c) {
        if (!x)
            throw std::invalid_argument("literal must be nonzero");
        int v = std::abs(x) - 1;
        while (v >= impl_->formula->nVars())
            impl_->formula->newVar();
        lits.push(mkLit(v, x < 0));
    }
    if (soft) {
        if (weight <= 0)
            throw std::invalid_argument("soft weight must be positive");
        impl_->formula->addSoftClause((uint64_t)weight, lits);
        impl_->formula->updateSumWeights((uint64_t)weight);
        impl_->formula->setMaximumWeight((uint64_t)weight);
        if (weight > 1)
            impl_->formula->setProblemType(_WEIGHTED_);
    } else
        impl_->formula->addHardClause(lits);
}
bool TTOpenWBOIncNative::solve() {
    if (!impl_->solver) {
        apply_defaults(impl_->formula);
        if (impl_->formula->getProblemType() == _UNWEIGHTED_) {
            impl_->kind = Kind::Obv;
            impl_->solver =
                new ModelAccessOBV(_VERBOSITY_MINIMAL_, _CARD_MTOTALIZER_, 1000, INT32_MAX, true);
        } else {
            impl_->kind = Kind::Linear;
            impl_->solver =
                new ModelAccessLinear(_VERBOSITY_MINIMAL_, true, _CARD_TOTALIZER_, _PB_GTE_,
                                      ClusterAlg::_DIVISIVE_, Statistics::_MEAN_, 100000);
        }
        impl_->solver->loadFormula(impl_->formula);
        if (impl_->formula->getProblemType() != _UNWEIGHTED_)
            static_cast<ModelAccessLinear *>(impl_->solver)->initializeCluster();
        impl_->solver->setPrintModel(true);
        impl_->transferred = true;
    }
    impl_->solver->search();
    return impl_->model().size() > 0;
}
uint64_t TTOpenWBOIncNative::cost() const {
    if (!impl_->solver)
        throw std::runtime_error("solver has not been run");
    return impl_->solver->getUB();
}
bool TTOpenWBOIncNative::value(int v) const {
    if (!impl_->solver)
        throw std::runtime_error("solver has not been run");
    if (v > 0 && v <= impl_->formula->nVars())
        return impl_->model()[v - 1] == l_True;
    return false;
}
