#include "coretrail/glucose_backend.hpp"

#include "core/Solver.h"

namespace coretrail {

struct GlucoseBackend::Impl {
    Glucose::Solver solver;
    SatResult last_status{SatResult::UNKNOWN};
    bool inconsistent{false};
};

static inline Glucose::Lit to_lit(int l) {
    return l > 0 ? Glucose::mkLit(l, false) : Glucose::mkLit(-l, true);
}

GlucoseBackend::GlucoseBackend() : p_(new Impl()) {}

GlucoseBackend::~GlucoseBackend() {
    delete p_;
    p_ = nullptr;
}

void GlucoseBackend::ensure_vars(int max_var) {
    while (p_->solver.nVars() < max_var + 1) {
        p_->solver.newVar();
    }
}

bool GlucoseBackend::add_clause(const std::vector<int>& clause) {
    if (p_->inconsistent) return false;
    int maxv = 0;
    for (int l : clause) {
        int v = l > 0 ? l : -l;
        if (v > maxv) maxv = v;
    }
    ensure_vars(maxv);
    Glucose::vec<Glucose::Lit> cl;
    for (int l : clause) cl.push(to_lit(l));
    const bool accepted = p_->solver.addClause(cl);
    if (!accepted) p_->inconsistent = true;
    return accepted;
}

bool GlucoseBackend::solve(const std::vector<int>& assumptions) {
    if (p_->inconsistent) {
        p_->last_status = SatResult::UNSAT;
        return false;
    }
    int maxv = 0;
    for (int l : assumptions) {
        int v = l > 0 ? l : -l;
        if (v > maxv) maxv = v;
    }
    ensure_vars(maxv);
    Glucose::vec<Glucose::Lit> as;
    for (int l : assumptions) as.push(to_lit(l));
    Glucose::lbool st = p_->solver.solveLimited(as);
    if (st == l_True) {
        p_->last_status = SatResult::SAT;
        return true;
    }
    if (st == l_False) {
        p_->last_status = SatResult::UNSAT;
        return false;
    }
    p_->last_status = SatResult::UNKNOWN;
    return false;
}

std::pair<bool, std::vector<int>> GlucoseBackend::prop_check(const std::vector<int>& assumptions, int phase_saving) {
    if (p_->inconsistent) {
        p_->last_status = SatResult::UNSAT;
        return {false, {}};
    }
    int maxv = 0;
    for (int l : assumptions) {
        int v = l > 0 ? l : -l;
        if (v > maxv) maxv = v;
    }
    ensure_vars(maxv);
    Glucose::vec<Glucose::Lit> as;
    for (int l : assumptions) as.push(to_lit(l));

    Glucose::vec<Glucose::Lit> pr;
    bool st = p_->solver.prop_check(as, pr, phase_saving);

    std::vector<int> out;
    out.reserve(pr.size());
    for (int i = 0; i < pr.size(); ++i) {
        int v = Glucose::var(pr[i]);
        int lit = Glucose::sign(pr[i]) ? -v : v;
        out.push_back(lit);
    }
    return {st, std::move(out)};
}

SatResult GlucoseBackend::solve_limited(const std::vector<int>& assumptions) {
    if (p_->inconsistent) {
        p_->last_status = SatResult::UNSAT;
        return p_->last_status;
    }
    int maxv = 0;
    for (int l : assumptions) {
        int v = l > 0 ? l : -l;
        if (v > maxv) maxv = v;
    }
    ensure_vars(maxv);
    Glucose::vec<Glucose::Lit> as;
    for (int l : assumptions) as.push(to_lit(l));

    Glucose::lbool st = p_->solver.solveLimited(as);
    if (st == l_True) {
        p_->last_status = SatResult::SAT;
    } else if (st == l_False) {
        p_->last_status = SatResult::UNSAT;
    } else {
        p_->last_status = SatResult::UNKNOWN;
    }
    return p_->last_status;
}

void GlucoseBackend::set_time_limit(double seconds) {
    p_->solver.setTimeLimit(seconds);
}

void GlucoseBackend::clear_time_limit() {
    p_->solver.clearTimeLimit();
}

bool GlucoseBackend::time_limit_expired() const {
    return p_->solver.timeLimitExpired();
}

void GlucoseBackend::set_conf_budget(std::int64_t conflicts) {
    p_->solver.setConfBudget(conflicts);
}

void GlucoseBackend::budget_off() {
    p_->solver.budgetOff();
}

std::vector<int> GlucoseBackend::get_model() const {
    std::vector<int> m;
    const auto& vm = p_->solver.model;
    m.reserve(vm.size());
    Glucose::lbool True = Glucose::lbool((uint8_t)0);
    for (int i = 1; i < vm.size(); ++i) {
        if (vm[i] == True) m.push_back(i);
        else m.push_back(-i);
    }
    return m;
}

std::vector<int> GlucoseBackend::get_core() const {
    std::vector<int> c;
    const auto& vc = p_->solver.conflict;
    c.reserve(vc.size());
    for (int i = 0; i < vc.size(); ++i) {
        int v = Glucose::var(vc[i]);
        int l = Glucose::sign(vc[i]) ? v : -v;
        c.push_back(l);
    }
    return c;
}

SatResult GlucoseBackend::get_last_status() const {
    return p_->last_status;
}

void GlucoseBackend::interrupt() {
    p_->solver.interrupt();
}

void GlucoseBackend::clear_interrupt() {
    p_->solver.clearInterrupt();
}

void GlucoseBackend::set_interrupt_probe(InterruptProbe probe) {
    p_->solver.setInterruptProbe(probe);
}

void GlucoseBackend::reset() {
    delete p_;
    p_ = new Impl();
}

}  // namespace coretrail
