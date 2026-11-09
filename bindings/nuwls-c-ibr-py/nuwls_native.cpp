#include "nuwls_native.h"
#include "algorithms/Alg_BLS.h"
#include "MaxSATFormula.h"
#include <algorithm>
#include <cstdlib>
#include <stdexcept>
#include <unordered_map>
namespace nuwls_native {
using namespace openwbo;
struct Weight {
    bool has;
    long long value;
};
using Clause = std::pair<std::vector<int>, Weight>;
class BLSEx : public BLS {
  public:
    BLSEx() : BLS(0, _CARD_MTOTALIZER_, 100000, 50, false) {}
    bool has_model() const { return nbSatisfiable > 0; }
    std::vector<int> model_ext() const {
        std::vector<int> r;
        r.reserve(model.size());
        for (int i = 0; i < model.size(); ++i)
            r.push_back(model[i] == l_True ? i + 1 : -(i + 1));
        return r;
    }
    bool value_ext(int v) const {
        if (v <= 0)
            throw std::invalid_argument("Variable id must be >= 1");
        int i = v - 1;
        return i < model.size() && model[i] == l_True;
    }
    uint64_t cost() { return getCost(); }
};
class Solver::Impl {
  public:
    int n = 0;
    std::vector<Clause> clauses;
    std::unique_ptr<BLSEx> solver;
};
Solver::Solver() : impl_(new Impl()) {}
Solver::~Solver() = default;
int Solver::new_var() { return ++impl_->n; }
void Solver::set_n_input_vars(unsigned int n) {
    if (n > static_cast<unsigned>(INT32_MAX))
        throw std::overflow_error("input variable count exceeds supported range");
    if (static_cast<int>(n) > impl_->n)
        impl_->n = static_cast<int>(n);
}
void Solver::add_clause(const std::vector<int> &c, bool has, long long w) {
    for (int lit : c)
        if (!lit || lit == INT32_MIN)
            throw std::invalid_argument("Literal 0 is invalid");
    if (has && w <= 0)
        throw std::invalid_argument("Soft weight must be positive");
    int maxv = impl_->n;
    for (int lit : c)
        maxv = std::max(maxv, std::abs(lit));
    impl_->clauses.push_back({c, {has, w}});
    impl_->n = maxv;
}
bool Solver::solve(const std::vector<int> &assumptions, bool has_assumptions) {
    for (int lit : assumptions)
        if (!lit || lit == INT32_MIN)
            throw std::invalid_argument("Assumption literal 0 is invalid");
    std::vector<Clause> norm;
    std::unordered_map<int, long long> units;
    for (const auto &cr : impl_->clauses) {
        if (!cr.second.has)
            norm.push_back(cr);
        else if (cr.first.size() == 1)
            units[cr.first[0]] = cr.second.value;
        else
            norm.push_back(cr);
    }
    for (const auto &kv : units)
        norm.push_back({{kv.first}, {true, kv.second}});
    uint64_t sum = 0;
    for (const auto &cr : norm)
        if (cr.second.has) {
            uint64_t w = static_cast<uint64_t>(cr.second.value);
            if (sum > UINT64_MAX - w)
                throw std::overflow_error("sum of soft weights exceeds uint64 range");
            sum += w;
        }
    auto *f = new MaxSATFormula();
    for (int i = 0; i < impl_->n; ++i)
        f->newVar();
    std::vector<Clause> hard, nonunit, unit;
    bool weighted = false;
    for (const auto &cr : norm) {
        if (!cr.second.has)
            hard.push_back(cr);
        else {
            if (cr.second.value != 1)
                weighted = true;
            if (cr.first.size() == 1)
                unit.push_back(cr);
            else
                nonunit.push_back(cr);
        }
    }
    auto append = [&](const Clause &cr) {
        vec<Lit> lits;
        lits.capacity(cr.first.size());
        for (int x : cr.first) {
            int v = std::abs(x) - 1;
            while (v >= f->nVars())
                f->newVar();
            lits.push(mkLit(v, x < 0));
        }
        if (cr.second.has)
            f->addSoftClause(static_cast<uint64_t>(cr.second.value), lits);
        else
            f->addHardClause(lits);
    };
    for (const auto &cr : hard)
        append(cr);
    for (const auto &cr : nonunit)
        append(cr);
    for (const auto &cr : unit)
        append(cr);
    if (has_assumptions)
        for (int a : assumptions)
            append({{a}, {false, 0}});
    f->setProblemType(weighted ? _WEIGHTED_ : _UNWEIGHTED_);
    f->setHardWeight(sum == UINT64_MAX ? UINT64_MAX : sum + 1);
    impl_->solver.reset(new BLSEx());
    impl_->solver->loadFormula(f);
    impl_->solver->search();
    return impl_->solver->has_model();
}
int Solver::get_status() const {
    return !impl_->solver                   ? 60
           : impl_->solver->search_complete ? (impl_->solver->has_model() ? 30 : 20)
                                            : (impl_->solver->has_model() ? 10 : 0);
}
uint64_t Solver::get_cost() { return impl_->solver ? impl_->solver->cost() : 0; }
bool Solver::get_value(int v) const { return impl_->solver ? impl_->solver->value_ext(v) : false; }
std::vector<int> Solver::get_model() const {
    return impl_->solver ? impl_->solver->model_ext() : std::vector<int>{};
}
} // namespace nuwls_native
