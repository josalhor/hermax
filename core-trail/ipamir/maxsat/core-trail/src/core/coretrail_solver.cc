#include "coretrail/coretrail_solver.hpp"

#include <algorithm>
#include <cmath>
#include <sstream>
#include <stdexcept>

#include "clset.hh"
#include "dag.hh"
#include "itot.hh"

namespace coretrail {

namespace {

static inline bool contains_lit(const std::vector<int>& v, int lit) {
    return std::find(v.begin(), v.end(), lit) != v.end();
}

static inline void append_all(std::vector<int>* dst, const std::vector<int>& src) {
    dst->insert(dst->end(), src.begin(), src.end());
}

static inline void dedup_lits_inplace(std::vector<int>* lits) {
    std::unordered_set<int> seen;
    std::vector<int> out;
    out.reserve(lits->size());
    for (int l : *lits) {
        if (seen.insert(l).second) out.push_back(l);
    }
    lits->swap(out);
}

static inline std::string lits_key(const std::vector<int>& lits) {
    std::vector<int> sorted = lits;
    std::sort(sorted.begin(), sorted.end());
    std::ostringstream oss;
    for (size_t i = 0; i < sorted.size(); ++i) {
        if (i) oss << ',';
        oss << sorted[i];
    }
    return oss.str();
}

static inline std::vector<int> without_index(const std::vector<int>& v, size_t idx) {
    std::vector<int> out;
    out.reserve(v.size() - 1);
    for (size_t i = 0; i < v.size(); ++i) {
        if (i != idx) out.push_back(v[i]);
    }
    return out;
}

static inline int blomap_value(const std::string& blo) {
    if (blo == "none") return 0;
    if (blo == "basic") return 1;
    if (blo == "div") return 3;
    if (blo == "cluster") return 5;
    if (blo == "full") return 7;
    throw std::invalid_argument("Unknown BLO strategy");
}

}  // namespace

void ConsequenceMap::add(int lit, const std::shared_ptr<Consequence>& c) {
    if (!c) return;
    map_[lit].push_back(c);
    inverse_[c->counter].push_back(lit);
}

void ConsequenceMap::remove(int consequence_counter) {
    auto it = inverse_.find(consequence_counter);
    if (it == inverse_.end()) return;
    for (int lit : it->second) {
        auto mit = map_.find(lit);
        if (mit == map_.end()) continue;
        auto& v = mit->second;
        v.erase(std::remove_if(v.begin(), v.end(), [consequence_counter](const std::shared_ptr<Consequence>& c) {
            return c && c->counter == consequence_counter;
        }), v.end());
    }
    inverse_.erase(it);
}

void ConsequenceMap::bulk_remove(const std::vector<int>& counters) {
    std::unordered_set<int> cs(counters.begin(), counters.end());
    std::unordered_set<int> lits;
    for (int c : counters) {
        auto it = inverse_.find(c);
        if (it == inverse_.end()) continue;
        for (int l : it->second) lits.insert(l);
    }
    for (int l : lits) {
        auto mit = map_.find(l);
        if (mit == map_.end()) continue;
        auto& v = mit->second;
        v.erase(std::remove_if(v.begin(), v.end(), [&cs](const std::shared_ptr<Consequence>& c) {
            return c && cs.find(c->counter) != cs.end();
        }), v.end());
    }
    for (int c : counters) inverse_.erase(c);
}

std::shared_ptr<Consequence> ConsequenceMap::new_consequence(long weight, const std::vector<int>& core) {
    auto c = std::make_shared<Consequence>();
    c->counter = counter_++;
    c->weight = weight;
    c->core = core;
    return c;
}

const std::vector<std::shared_ptr<Consequence>>* ConsequenceMap::get(int lit) const {
    auto it = map_.find(lit);
    if (it == map_.end()) return nullptr;
    return &it->second;
}

std::vector<std::shared_ptr<Consequence>> ConsequenceMap::all() const {
    std::unordered_map<int, std::shared_ptr<Consequence>> uniq;
    for (const auto& kv : map_) {
        for (const auto& c : kv.second) {
            if (!c) continue;
            uniq.emplace(c->counter, c);
        }
    }
    std::vector<std::shared_ptr<Consequence>> out;
    out.reserve(uniq.size());
    for (const auto& kv : uniq) out.push_back(kv.second);
    return out;
}

CoreTrailSolver::CoreTrailSolver(CoreTrailOptions opts)
    : opts_(std::move(opts)) {
    verbose_ = opts_.verbose;
    exhaust_ = opts_.exhaust;
    solver_name_ = opts_.solver;
    adapt_ = opts_.adapt;
    minz_ = opts_.minz;
    trim_ = opts_.trim;
    core_memory_ = opts_.core_memory;
    core_replay_ = opts_.core_replay;
    full_stratified_ = opts_.full_stratified;
    exploit_overlap_ = opts_.exploit_overlap;
    bstr_ = blomap_value(opts_.blo);
    hard_ = false;
    done_ = 0;
    levl_ = 0;
}

void CoreTrailSolver::initialize_external_vars(int nv) {
    ensure_open("initialize_external_vars");
    if (nv <= 0) return;
    for (int v = 1; v <= nv; ++v) {
        if (e2i_.find(v) == e2i_.end()) e2i_[v] = v;
        if (i2e_.find(v) == i2e_.end()) i2e_[v] = v;
    }
    if (pool_top_ < nv) pool_top_ = nv;
}

[[noreturn]] void CoreTrailSolver::not_impl(const char* fn) const {
    std::ostringstream oss;
    oss << fn << " is not implemented in pure C++ core yet";
    throw std::runtime_error(oss.str());
}

void CoreTrailSolver::ensure_open(const char* fn) const {
    if (closed_) {
        std::ostringstream oss;
        oss << fn << " called on closed solver";
        throw std::runtime_error(oss.str());
    }
}

void CoreTrailSolver::set_weight(int lit, long weight) {
    auto it = wght_.find(lit);
    if (it == wght_.end()) {
        wght_order_.push_back(lit);
        wght_[lit] = weight;
        return;
    }
    it->second = weight;
}

void CoreTrailSolver::erase_weight(int lit) {
    auto it = wght_.find(lit);
    if (it == wght_.end()) return;
    wght_.erase(it);
    wght_order_.erase(std::remove(wght_order_.begin(), wght_order_.end(), lit), wght_order_.end());
}

void CoreTrailSolver::ensure_backend_synced() {
    for (const auto& cl : pending_clauses_) {
        (void)sat_.add_clause(cl);
    }
    pending_clauses_.clear();
}

std::vector<int> CoreTrailSolver::canonical_assumptions(const std::vector<int>& assumptions) const {
    std::vector<int> normalized;
    normalized.reserve(assumptions.size());
    for (int lit : assumptions) {
        if (lit == 0) throw std::invalid_argument("0 cannot be an assumption");
        normalized.push_back(lit);
    }
    std::sort(normalized.begin(), normalized.end(), [](int left, int right) {
        const int left_var = std::abs(left);
        const int right_var = std::abs(right);
        if (left_var != right_var) return left_var < right_var;
        return left < right;
    });
    normalized.erase(std::unique(normalized.begin(), normalized.end()), normalized.end());
    return normalized;
}

void CoreTrailSolver::mark_query_dirty() noexcept {
    query_dirty_ = true;
    optimization_started_ = false;
    optimization_complete_ = false;
    terminal_status_ = SolveStatus::UNKNOWN;
    level_active_ = false;
    incumbent_cost_.reset();
    incumbent_model_.clear();
    model_.clear();
    model_set_.clear();
    status_ = SolveStatus::UNKNOWN;
}

bool CoreTrailSolver::stop_or_interrupted(bool check_sat_unknown) {
    if (interrupt_probe_ != nullptr && interrupt_probe_()) {
        request_stop();
    }
    if (stop_requested_.load(std::memory_order_relaxed)) {
        if (incumbent_cost_.has_value()) {
            restore_incumbent();
            status_ = SolveStatus::INTERRUPTED_SAT;
        } else {
            status_ = SolveStatus::INTERRUPTED;
        }
        interrupted_last_solve_ = true;
        return true;
    }
    if (sat_.time_limit_expired()) {
        if (incumbent_cost_.has_value()) {
            restore_incumbent();
            status_ = SolveStatus::INTERRUPTED_SAT;
        } else {
            status_ = SolveStatus::INTERRUPTED;
        }
        interrupted_last_solve_ = true;
        return true;
    }
    if (check_sat_unknown && sat_.get_last_status() == SatResult::UNKNOWN) {
        if (incumbent_cost_.has_value()) {
            restore_incumbent();
            status_ = SolveStatus::INTERRUPTED_SAT;
        } else {
            status_ = SolveStatus::INTERRUPTED;
        }
        interrupted_last_solve_ = true;
        return true;
    }
    return false;
}

void CoreTrailSolver::publish_candidate() {
    const std::vector<int> internal = sat_.get_model();
    std::vector<int> external;
    external.reserve(internal.size());
    for (int lit : internal) {
        const auto it = i2e_.find(std::abs(lit));
        if (it != i2e_.end()) external.push_back(lit > 0 ? it->second : -it->second);
    }
    std::unordered_set<int> present;
    present.reserve(external.size() * 2U + 1U);
    for (int lit : external) present.insert(std::abs(lit));
    for (const auto& [external_var, internal_var] : e2i_) {
        (void)internal_var;
        if (present.insert(external_var).second) external.push_back(external_var);
    }
    std::sort(external.begin(), external.end(), [](int a, int b) { return std::abs(a) < std::abs(b); });
    const long exact_cost = objective_.evaluate(external);
    if (incumbent_cost_.has_value() && exact_cost >= *incumbent_cost_) return;
    incumbent_cost_ = exact_cost;
    incumbent_model_ = std::move(external);
}

void CoreTrailSolver::restore_incumbent() {
    if (!incumbent_cost_.has_value()) return;
    model_ = incumbent_model_;
    model_set_.clear();
    for (int lit : model_) model_set_.insert(lit);
}

int CoreTrailSolver::map_extlit(int lit) {
    int v = std::abs(lit);
    auto it = e2i_.find(v);
    int iv;
    if (it != e2i_.end()) {
        iv = it->second;
    } else {
        iv = ++pool_top_;
        e2i_[v] = iv;
        i2e_[iv] = v;
    }
    return lit >= 0 ? iv : -iv;
}

CoreSplit CoreTrailSolver::split_core_assumptions(const std::vector<int>& core) const {
    CoreSplit out;
    out.sels_ass.reserve(core.size());
    out.reduced_core.reserve(core.size());
    out.impossible_soft.reserve(core.size());

    std::unordered_set<int> ass_set(assumptions_.begin(), assumptions_.end());
    std::unordered_set<int> imp_set(impossible_lits_.begin(), impossible_lits_.end());

    for (int l : core) {
        if (ass_set.find(l) != ass_set.end()) {
            out.sels_ass.push_back(l);
        } else if (imp_set.find(l) != imp_set.end()) {
            out.impossible_soft.push_back(l);
        } else {
            out.reduced_core.push_back(l);
        }
    }
    return out;
}

std::shared_ptr<Consequence> CoreTrailSolver::new_consequence(std::optional<long> weight) {
    long w = weight.has_value() ? *weight : minw_;
    auto c = lit_to_consequence_.new_consequence(w, original_core_);
    for (int l : original_core_) {
        lit_to_consequence_.add(l, c);
    }
    return c;
}

void CoreTrailSolver::filter_assumps() {
    std::vector<int> new_sels;
    new_sels.reserve(sels_.size());
    for (int l : sels_) {
        if (garbage_.find(l) == garbage_.end()) new_sels.push_back(l);
    }
    sels_.swap(new_sels);

    std::vector<int> new_sums;
    new_sums.reserve(sums_.size());
    for (int l : sums_) {
        if (garbage_.find(l) == garbage_.end()) new_sums.push_back(l);
    }
    sums_.swap(new_sums);

    for (int l : garbage_) {
        auto ib = bnds_.find(l);
        if (ib != bnds_.end()) {
            bnds_history_[l] = ib->second;
            bnds_.erase(ib);
        }
        erase_weight(l);
    }

    for (int l : garbage_) {
        sels_set_.erase(l);
    }

    garbage_.clear();
    normalize_active_objective_assumptions();
}

void CoreTrailSolver::normalize_active_objective_assumptions() {
    dedup_lits_inplace(&sels_);
    dedup_lits_inplace(&sums_);
    sels_set_.clear();
    sels_set_.insert(sels_.begin(), sels_.end());
}

bool CoreTrailSolver::remove_contradictory_objective_assumptions() {
    auto remove_weight = [&](int lit, long delta, const std::shared_ptr<Consequence>& c) {
        if (delta <= 0) return;
        auto it = wght_.find(lit);
        if (it == wght_.end() || it->second < delta) {
            throw std::runtime_error("remove_contradictory_objective_assumptions: bad weight delta");
        }

        c->wdelta[lit] -= delta;

        if (it->second == delta) {
            garbage_.insert(lit);
            c->removed_lits.push_back(lit);
        } else {
            it->second -= delta;
            if (done_ != -1 && levl_ >= 0 && levl_ < static_cast<int>(blop_.size()) && it->second < blop_[levl_]) {
                wstr_[it->second].push_back(lit);
            }
        }
    };

    bool changed = true;
    while (changed) {
        changed = false;
        normalize_active_objective_assumptions();

        std::unordered_set<int> base;
        base.reserve(assumptions_.size() + impossible_lits_.size());
        base.insert(assumptions_.begin(), assumptions_.end());
        base.insert(impossible_lits_.begin(), impossible_lits_.end());
        auto is_base = [&](int l) -> bool { return base.find(l) != base.end(); };

        // Case 1: complementary active objective pair l and -l (objective-only).
        std::vector<int> active;
        active.reserve(sels_.size() + sums_.size());
        for (int l : sels_) {
            if (is_active_objective_lit(l) && !is_base(l)) active.push_back(l);
        }
        for (int l : sums_) {
            if (is_active_objective_lit(l) && !is_base(l)) active.push_back(l);
        }
        std::unordered_set<int> active_set(active.begin(), active.end());

        for (int l : active) {
            int nl = -l;
            if (l > nl) continue;
            if (active_set.find(nl) == active_set.end()) continue;
            if (is_base(l) || is_base(nl)) continue;

            long wl = wght_.at(l);
            long wnl = wght_.at(nl);
            long minw = std::min(wl, wnl);
            if (minw <= 0) continue;

            original_core_ = {l, nl};
            auto c = new_consequence(minw);

            cost_ += minw;
            garbage_.clear();
            remove_weight(l, minw, c);
            remove_weight(nl, minw, c);
            filter_assumps();
            original_core_.clear();

            changed = true;
            break;
        }

        if (changed) continue;

        // Case 2: base literal l falsifies objective literal -l.
        for (int l : base) {
            int obj = -l;
            if (is_base(obj)) continue;
            if (!is_active_objective_lit(obj)) continue;

            long w = wght_.at(obj);
            if (w <= 0) continue;

            original_core_ = {l, obj};
            auto c = new_consequence(w);

            cost_ += w;
            garbage_.clear();
            remove_weight(obj, w, c);
            filter_assumps();
            original_core_.clear();

            changed = true;
            break;
        }
    }
    return true;
}

bool CoreTrailSolver::is_active_objective_lit(int l) const {
    auto iw = wght_.find(l);
    if (iw == wght_.end() || iw->second <= 0) return false;
    if (sels_set_.find(l) != sels_set_.end()) return true;
    if (contains_lit(sums_, l)) return true;
    return false;
}

long CoreTrailSolver::disable_old_consequences() {
    std::unordered_set<int> conflicting_lits;
    for (const auto& kv : transition_weights_) conflicting_lits.insert(kv.first);
    std::unordered_set<int> cur_ass(assumptions_.begin(), assumptions_.end());
    for (int l : last_assumptions_) {
        if (cur_ass.find(l) == cur_ass.end()) {
            conflicting_lits.insert(l);
        }
    }
    for (int l : assumptions_) {
        conflicting_lits.insert(-l);
    }
    std::unordered_set<int> new_lits = conflicting_lits;

    std::unordered_map<int, std::shared_ptr<Consequence>> consequences_to_disable;
    bool stable = false;
    while (!stable) {
        stable = true;
        std::unordered_set<int> left_to_mark = std::move(new_lits);
        new_lits.clear();

        for (int l : left_to_mark) {
            const std::vector<std::shared_ptr<Consequence>>* cons = lit_to_consequence_.get(l);
            if (cons == nullptr) continue;
            for (const auto& consequence : *cons) {
                if (!consequence) continue;
                if (consequences_to_disable.find(consequence->counter) != consequences_to_disable.end()) {
                    continue;
                }
                consequences_to_disable.emplace(consequence->counter, consequence);
                stable = false;

                for (int added_lit : consequence->added_lits) {
                    if (conflicting_lits.insert(added_lit).second) {
                        new_lits.insert(added_lit);
                    }
                }
                for (const auto& wd : consequence->wdelta) {
                    if (wd.second < 0) {
                        int removed_lit = wd.first;
                        if (conflicting_lits.insert(removed_lit).second) {
                            new_lits.insert(removed_lit);
                        }
                    }
                }
            }
        }
    }

    long max_weight = 0;
    if (consequences_to_disable.empty()) return max_weight;

    std::vector<std::shared_ptr<Consequence>> sorted;
    sorted.reserve(consequences_to_disable.size());
    for (const auto& kv : consequences_to_disable) sorted.push_back(kv.second);
    std::sort(sorted.begin(), sorted.end(), [](const std::shared_ptr<Consequence>& a, const std::shared_ptr<Consequence>& b) {
        return a->counter > b->counter;
    });

    for (const auto& consequence : sorted) {
        std::vector<int> new_sels;
        new_sels.reserve(sels_.size());
        for (int l : sels_) {
            if (!contains_lit(consequence->added_lits, l)) new_sels.push_back(l);
        }
        sels_.swap(new_sels);
        for (int l : consequence->added_lits) sels_set_.erase(l);

        std::vector<int> new_sums;
        new_sums.reserve(sums_.size());
        for (int l : sums_) {
            if (!contains_lit(consequence->added_lits, l)) new_sums.push_back(l);
        }
        sums_.swap(new_sums);

        std::vector<int> new_impossible;
        new_impossible.reserve(impossible_lits_.size());
        for (int l : impossible_lits_) {
            if (!contains_lit(consequence->added_lits, l)) new_impossible.push_back(l);
        }
        impossible_lits_.swap(new_impossible);

        for (int l : consequence->removed_lits) {
            if (all_sels_.find(l) != all_sels_.end() || transition_weights_.find(l) != transition_weights_.end()) {
                if (sels_set_.find(l) == sels_set_.end()) {
                    sels_.push_back(l);
                    sels_set_.insert(l);
                }
            } else {
                if (!contains_lit(sums_, l)) {
                    sums_.push_back(l);
                    if (bnds_.find(l) == bnds_.end()) {
                        auto ih = bnds_history_.find(l);
                        if (ih == bnds_history_.end()) {
                            throw std::runtime_error("disable_old_consequences: missing bound history for restored sum");
                        }
                        bnds_[l] = ih->second;
                        bnds_history_.erase(ih);
                    }
                    if (tobj_.find(l) == tobj_.end()) {
                        throw std::runtime_error("disable_old_consequences: missing totalizer object for restored sum");
                    }
                    if (swgt_.find(l) == swgt_.end()) {
                        throw std::runtime_error("disable_old_consequences: missing swgt for restored sum");
                    }
                }
            }
        }

        cost_ -= consequence->weight;

        for (const auto& wd : consequence->wdelta) {
            int l = wd.first;
            long delta = wd.second;
            auto iw = wght_.find(l);
            if (iw != wght_.end()) {
                iw->second -= delta;
                max_weight = std::max(max_weight, iw->second);
                if (iw->second < 0) {
                    throw std::runtime_error("disable_old_consequences: negative weight after rollback");
                }
                if (iw->second == 0) erase_weight(l);
            } else {
                if (!(delta < 0)) {
                    throw std::runtime_error("disable_old_consequences: expected negative delta when re-adding missing weight");
                }
                set_weight(l, -delta);
                max_weight = std::max(max_weight, wght_.at(l));
            }
        }

        for (int l : consequence->created_sum_deltas) {
            bnds_.erase(l);
            tobj_.erase(l);
            lit_to_totalizerid_.erase(l);
            auto is = swgt_.find(l);
            if (is == swgt_.end()) {
                throw std::runtime_error("disable_old_consequences: missing swgt for created_sum_deltas literal");
            }
            swgt_.erase(is);
        }
    }

    std::vector<int> to_remove;
    to_remove.reserve(sorted.size());
    for (const auto& c : sorted) to_remove.push_back(c->counter);
    lit_to_consequence_.bulk_remove(to_remove);

    for (int l : sels_) {
        auto iw = wght_.find(l);
        if (iw == wght_.end() || iw->second <= 0) {
            throw std::runtime_error("disable_old_consequences: selector is not active with positive weight");
        }
        if (original_wght_.find(l) == original_wght_.end()) {
            throw std::runtime_error("disable_old_consequences: selector missing original weight");
        }
    }
    for (int l : sums_) {
        auto iw = wght_.find(l);
        if (iw == wght_.end() || iw->second <= 0) {
            throw std::runtime_error("disable_old_consequences: sum is not active with positive weight");
        }
        if (swgt_.find(l) == swgt_.end()) throw std::runtime_error("disable_old_consequences: sum missing swgt");
        if (tobj_.find(l) == tobj_.end()) throw std::runtime_error("disable_old_consequences: sum missing tobj");
        if (bnds_.find(l) == bnds_.end()) throw std::runtime_error("disable_old_consequences: sum missing bound");
    }
    for (int l : wght_order_) {
        auto it = wght_.find(l);
        if (it == wght_.end()) continue;
        if (it->second <= 0) throw std::runtime_error("disable_old_consequences: non-positive weight after rollback");
    }

    if (core_replay_ > 0 && !sorted.empty()) {
        std::sort(sorted.begin(), sorted.end(), [](const std::shared_ptr<Consequence>& a, const std::shared_ptr<Consequence>& b) {
            return a->counter < b->counter;
        });
        std::vector<std::vector<int>> core_epoch;
        core_epoch.reserve(sorted.size());
        for (const auto& c : sorted) core_epoch.push_back(c->core);
        if (core_history_.size() >= static_cast<size_t>(core_replay_)) {
            core_history_.pop_front();
        }
        core_history_.push_back(std::move(core_epoch));
    }

    return max_weight;
}

bool CoreTrailSolver::redo_conflicting_assumptions() {
    if (core_replay_ <= 0) return false;

    std::unordered_set<int> base_set;
    base_set.insert(assumptions_.begin(), assumptions_.end());
    base_set.insert(sels_.begin(), sels_.end());
    base_set.insert(sums_.begin(), sums_.end());
    base_set.insert(impossible_lits_.begin(), impossible_lits_.end());

    for (auto epoch_it = core_history_.rbegin(); epoch_it != core_history_.rend(); ++epoch_it) {
        auto& epoch = *epoch_it;
        for (size_t i = 0; i < epoch.size(); ++i) {
            auto& core = epoch[i];
            if (core.empty()) continue;
            dedup_lits_inplace(&core);
            if (core.empty()) continue;

            bool could_core_happen = core.size() <= base_set.size();
            if (could_core_happen) {
                for (int l : core) {
                    if (base_set.find(l) == base_set.end()) {
                        could_core_happen = false;
                        break;
                    }
                }
            }
            if (!could_core_happen) continue;

            original_core_ = core;
            CoreSplit split = split_core_assumptions(original_core_);
            sels_ass_ = std::move(split.sels_ass);
            core_ = std::move(split.reduced_core);
            sels_impossible_ = std::move(split.impossible_soft);

            if (core_.empty()) {
                original_core_.clear();
                core_.clear();
                sels_ass_.clear();
                return false;
            }

            handle_core(false);
            if (!process_core()) return false;

            original_core_.clear();
            core_.clear();
            sels_ass_.clear();

            base_set.clear();
            base_set.insert(assumptions_.begin(), assumptions_.end());
            base_set.insert(sels_.begin(), sels_.end());
            base_set.insert(sums_.begin(), sums_.end());
            base_set.insert(impossible_lits_.begin(), impossible_lits_.end());

            core.clear();
        }
    }

    return true;
}

bool CoreTrailSolver::preprocess_unit_cores_from_base() {
    if (stop_or_interrupted()) return false;
    std::vector<int> base = assumptions_;
    append_all(&base, impossible_lits_);

    auto prop_res = sat_.prop_check(base, 2);
    bool st = prop_res.first;
    const std::vector<int>& props = prop_res.second;
    if (stop_or_interrupted()) return false;
    if (!st) {
        if (stop_or_interrupted(true)) return false;
        throw std::runtime_error("preprocess_unit_cores_from_base: base assumptions are UNSAT");
    }

    std::vector<int> forced;
    for (int p : props) {
        int s = -p;
        if (sels_set_.find(s) != sels_set_.end()) forced.push_back(s);
    }

    for (int s : forced) {
        if (sels_set_.find(s) == sels_set_.end() || wght_.find(s) == wght_.end()) {
            continue;
        }

        original_core_ = base;
        original_core_.push_back(s);
        CoreSplit split = split_core_assumptions(original_core_);
        sels_ass_ = std::move(split.sels_ass);
        core_ = std::move(split.reduced_core);
        sels_impossible_ = std::move(split.impossible_soft);

        if (core_.empty()) {
            continue;
        }

        handle_core(false);
        if (!process_core()) return false;
    }

    original_core_.clear();
    sels_ass_.clear();
    core_.clear();
    sels_impossible_.clear();
    return true;
}

void CoreTrailSolver::init_wstr() {
    wstr_.clear();
    for (int l : wght_order_) {
        auto it = wght_.find(l);
        if (it == wght_.end()) continue;
        wstr_[it->second].push_back(l);
    }

    blop_.clear();
    blop_.reserve(wstr_.size());
    for (const auto& kv : wstr_) blop_.push_back(kv.first);
    std::sort(blop_.begin(), blop_.end(), std::greater<long>());

    sdiv_ = blop_.empty() ? 0.0 : static_cast<double>(blop_.size()) / 2.0;
    done_ = 0;
}

void CoreTrailSolver::disable_strat_forever() {
    done_ = -1;
    levl_ = 0;

    std::vector<int> alive;
    for (int l : wght_order_) {
        auto it = wght_.find(l);
        if (it == wght_.end()) continue;
        if (it->second > 0) alive.push_back(l);
    }

    std::unordered_set<int> imp(impossible_lits_.begin(), impossible_lits_.end());
    sels_.clear();
    sums_.clear();
    for (int l : alive) {
        if (imp.find(l) != imp.end()) continue;
        if (original_wght_.find(l) != original_wght_.end()) sels_.push_back(l);
        else sums_.push_back(l);
    }
    sels_set_.clear();
    sels_set_.insert(sels_.begin(), sels_.end());
}

void CoreTrailSolver::next_level() {
    if (levl_ >= static_cast<int>(blop_.size())) {
        levl_ = -1;
        return;
    }

    int div_str = (bstr_ >> 1) & 1;
    int clu_str = (bstr_ >> 2) & 1;

    std::vector<int> cluster;
    cluster.push_back(levl_);

    int n = static_cast<int>(blop_.size());

    std::vector<int> cnt(n, 0);
    for (int i = 0; i < n; ++i) cnt[i] = static_cast<int>(wstr_[blop_[i]].size());

    std::vector<long> suf_cnt(n + 1, 0);
    std::vector<long> suf_sum(n + 1, 0);
    for (int i = n - 1; i >= 0; --i) {
        suf_cnt[i] = suf_cnt[i + 1] + cnt[i];
        suf_sum[i] = suf_sum[i + 1] + blop_[i] * cnt[i];
    }

    long numc = 0;
    long sumc = 0;
    if (clu_str) {
        numc = cnt[levl_];
        sumc = blop_[levl_] * cnt[levl_];
    }

    while (levl_ < n - 1) {
        long wght = blop_[levl_];
        int start = levl_ + 1;
        if (start < 0) {
            start += n;
            if (start < 0) start = 0;
        } else if (start > n) {
            start = n;
        }

        long numr = suf_cnt[start];
        long sumr = suf_sum[start];

        if (wght > sumr && sumr != 0) break;
        if (div_str && (n - levl_ - 1) > 0) {
            if (static_cast<double>(numr) / static_cast<double>(n - levl_ - 1) > sdiv_) break;
        }

        if (clu_str) {
            double left = std::fabs(static_cast<double>(wght) - static_cast<double>(sumc) / static_cast<double>(numc));
            double right = std::fabs(static_cast<double>(wght) - static_cast<double>(sumr) / static_cast<double>(numr));
            if (left > right) {
                levl_ = cluster.back();
                break;
            }
            cluster.push_back(levl_);
            numc += cnt[levl_];
            sumc += blop_[levl_] * cnt[levl_];
        }

        levl_ += 1;
    }
}

int CoreTrailSolver::activate_clauses(int beg) {
    int end = std::min(levl_ + 1, static_cast<int>(blop_.size()));

    for (int l = beg; l < end; ++l) {
        const auto& candidates = wstr_[blop_[l]];
        for (int sel : candidates) {
            auto iw = wght_.find(sel);
            if (iw == wght_.end()) continue;
            if (iw->second != blop_[l]) continue;

            if (original_wght_.find(sel) != original_wght_.end()) {
                if (sels_set_.insert(sel).second) sels_.push_back(sel);
            } else {
                if (!contains_lit(sums_, sel)) sums_.push_back(sel);
            }
        }
    }
    return end;
}

void CoreTrailSolver::finish_level() {
    throw std::runtime_error("Hardening is not supported in incremental MaxSAT");
}

int CoreTrailSolver::am1_get_or_create_selector(const std::vector<int>& clique) {
    std::string key = lits_key(clique);
    auto it = am1_sel_cache_.find(key);
    if (it != am1_sel_cache_.end()) return it->second;

    int sel = ++pool_top_;
    am1_sel_cache_[key] = sel;

    std::vector<int> cl;
    cl.reserve(clique.size() + 1);
    for (int l : clique) cl.push_back(-l);
    cl.push_back(-sel);
    (void)sat_.add_clause(cl);
    all_sels_.insert(sel);
    return sel;
}

void CoreTrailSolver::process_am1(std::vector<int> am1) {
    garbage_.clear();
    std::optional<long> cur_lvl_w = std::nullopt;
    if (done_ != -1 && levl_ >= 0 && levl_ < static_cast<int>(blop_.size())) {
        cur_lvl_w = blop_[levl_];
    }

    while (am1.size() > 1U) {
        minw_ = wght_.at(am1[0]);
        for (int l : am1) minw_ = std::min(minw_, wght_.at(l));
        int b = static_cast<int>(am1.size()) - 1;

        long penalty = minw_ * b;
        cost_ += penalty;

        original_core_ = am1;
        consequence_ = new_consequence(penalty);
        consequence_->is_clique = true;

        core_sels_ = am1;
        process_sels();

        std::vector<int> am1_new;
        for (int l : am1) if (garbage_.find(l) == garbage_.end()) am1_new.push_back(l);
        am1.swap(am1_new);

        int selv = am1_get_or_create_selector(rels_);

        if (original_wght_.find(selv) == original_wght_.end()) original_wght_[selv] = minw_;
        set_weight(selv, minw_);

        if (consequence_) {
            consequence_->added_lits.push_back(selv);
            consequence_->wdelta[selv] = minw_;
        }

        if (done_ != -1) wstr_[minw_].push_back(selv);

        if (!cur_lvl_w.has_value() || minw_ >= *cur_lvl_w) {
            if (sels_set_.find(selv) == sels_set_.end()) {
                sels_.push_back(selv);
                sels_set_.insert(selv);
            }
        }

    }

    if (done_ != -1 && cur_lvl_w.has_value()) {
        std::vector<int> to_deactivate;
        for (int l : am1) {
            auto iw = wght_.find(l);
            if (iw != wght_.end() && iw->second < *cur_lvl_w && sels_set_.find(l) != sels_set_.end()) {
                to_deactivate.push_back(l);
            }
        }
        if (!to_deactivate.empty()) {
            for (int l : to_deactivate) wstr_[wght_[l]].push_back(l);
            std::vector<int> new_sels;
            new_sels.reserve(sels_.size());
            for (int l : sels_) if (!contains_lit(to_deactivate, l)) new_sels.push_back(l);
            sels_.swap(new_sels);
            sels_set_.clear();
            sels_set_.insert(sels_.begin(), sels_.end());
        }
    }

    filter_assumps();
}

bool CoreTrailSolver::adapt_am1() {
    std::unordered_map<int, std::unordered_set<int>> conns;
    std::vector<int> confl;

    std::vector<int> sels_snapshot = sels_;
    for (int l1 : sels_snapshot) {
        if (stop_or_interrupted()) return false;
        auto prop_res = sat_.prop_check({l1}, 2);
        bool st = prop_res.first;
        const std::vector<int>& props = prop_res.second;
        if (stop_or_interrupted()) return false;

        if (st) {
            for (int l2 : props) {
                if (sels_set_.find(-l2) != sels_set_.end()) {
                    conns[l1].insert(-l2);
                    conns[-l2].insert(l1);
                }
            }
        } else {
            confl.push_back(l1);
        }
    }

    if (!confl.empty()) {
        std::unordered_set<int> confl_set(confl.begin(), confl.end());
        std::unordered_map<int, std::unordered_set<int>> ccopy;
        for (const auto& kv : conns) {
            if (confl_set.find(kv.first) != confl_set.end()) continue;
            std::unordered_set<int> cc;
            for (int x : kv.second) if (confl_set.find(x) == confl_set.end()) cc.insert(x);
            if (!cc.empty()) ccopy.emplace(kv.first, std::move(cc));
        }
        conns.swap(ccopy);

        for (int l : confl) {
            original_core_ = {l};
            core_ = {l};
            minw_ = wght_.at(l);
            core_sels_ = {l};
            core_sums_.clear();
            if (!process_core()) return false;
        }
    }

    int nof_am1 = 0;
    std::vector<int> len_am1;
    std::unordered_set<int> lits;
    for (const auto& kv : conns) lits.insert(kv.first);

    while (!lits.empty()) {
        int seed = *lits.begin();
        for (int l : lits) {
            if (conns[l].size() < conns[seed].size()) seed = l;
        }
        std::vector<int> am1 = {seed};

        std::vector<int> neigh(conns[seed].begin(), conns[seed].end());
        std::sort(neigh.begin(), neigh.end(), [&](int a, int b) {
            return conns[a].size() < conns[b].size();
        });

        for (int l : neigh) {
            if (lits.find(l) == lits.end()) continue;
            bool ok = true;
            for (size_t i = 1; i < am1.size(); ++i) {
                if (conns[l].find(am1[i]) == conns[l].end()) {
                    ok = false;
                    break;
                }
            }
            if (ok) am1.push_back(l);
        }

        for (int l : am1) lits.erase(l);
        std::unordered_set<int> am1set(am1.begin(), am1.end());
        for (auto& kv : conns) {
            for (int l : am1set) kv.second.erase(l);
        }

        if (am1.size() > 1U) {
            itot_dag_.add_mutex_clique(am1);
            process_am1(am1);
            nof_am1 += 1;
            len_am1.push_back(static_cast<int>(am1.size()));
        }
    }

    sels_set_.clear();
    sels_set_.insert(sels_.begin(), sels_.end());
    (void)nof_am1;
    (void)len_am1;
    return true;
}

bool CoreTrailSolver::trim_core() {
    for (int i = 0; i < trim_; ++i) {
        bool sat = sat_.solve(original_core_);
        if (sat) {
            throw std::runtime_error("trim_core: expected UNSAT under original_core assumptions");
        }
        if (stop_or_interrupted(true)) return false;

        std::vector<int> new_core = sat_.get_core();
        if (new_core.size() == original_core_.size()) {
            break;
        }
        original_core_ = std::move(new_core);
    }
    return true;
}

bool CoreTrailSolver::minimize_core() {
    CoreSplit split = split_core_assumptions(original_core_);
    std::vector<int> sels_ass = std::move(split.sels_ass);
    std::vector<int> obj_core = std::move(split.reduced_core);
    std::vector<int> impossible_soft = std::move(split.impossible_soft);

    if (minz_ && obj_core.size() > 1U) {
        std::sort(obj_core.begin(), obj_core.end(), [this](int a, int b) {
            return wght_.at(a) < wght_.at(b);
        });

        sat_.set_conf_budget(1000);

        original_core_.clear();
        append_all(&original_core_, sels_ass);
        append_all(&original_core_, impossible_soft);
        append_all(&original_core_, obj_core);

        size_t i = 0;
        while (i < original_core_.size()) {
            std::vector<int> to_test = without_index(original_core_, i);

            SatResult st = sat_.solve_limited(to_test);
            if (st == SatResult::UNSAT) {
                original_core_ = std::move(to_test);
            } else if (st == SatResult::SAT) {
                ++i;
            } else {
                sat_.budget_off();
                if (stop_requested_.load(std::memory_order_relaxed) || sat_.time_limit_expired()) {
                    (void)stop_or_interrupted();
                    return false;
                }
                // The conflict budget is only a minimization heuristic. Its
                // UNKNOWN result still leaves original_core_ as a valid core.
                break;
            }
        }

        sat_.budget_off();
    }
    return true;
}

void CoreTrailSolver::handle_core(bool remember) {
    (void)remember;

    if (core_.empty()) {
        minw_ = 0;
        core_sels_.clear();
        core_sums_.clear();
        return;
    }

    long cur_min = 0;
    bool have_min = false;
    for (int l : core_) {
        auto it = wght_.find(l);
        if (it == wght_.end()) {
            std::ostringstream oss;
            oss << "handle_core: missing weight for core literal " << l;
            throw std::runtime_error(oss.str());
        }
        if (!have_min || it->second < cur_min) {
            cur_min = it->second;
            have_min = true;
        }
    }
    minw_ = cur_min;

    core_sels_.clear();
    core_sums_.clear();
    core_sels_.reserve(core_.size());
    core_sums_.reserve(core_.size());
    for (int l : core_) {
        if (sels_set_.find(l) != sels_set_.end()) {
            core_sels_.push_back(l);
        } else {
            core_sums_.push_back(l);
        }
    }
}

bool CoreTrailSolver::get_core(bool skip_heuristics) {
    original_core_ = sat_.get_core();
    consequence_ = nullptr;

    if (original_core_.empty()) {
        throw std::runtime_error("get_core: empty core from UNSAT solve");
    }

    CoreSplit first = split_core_assumptions(original_core_);
    if (first.reduced_core.empty()) {
        core_.clear();
        return true;
    }

    if (!skip_heuristics) {
        if (!trim_core()) return false;
        if (!minimize_core()) return false;
    }

    CoreSplit second = split_core_assumptions(original_core_);
    sels_ass_ = std::move(second.sels_ass);
    core_ = std::move(second.reduced_core);
    sels_impossible_ = std::move(second.impossible_soft);
    if (core_.empty()) {
        return true;
    }

    handle_core(true);
    return true;
}

void CoreTrailSolver::process_sels() {
    rels_.clear();
    rels_.reserve(core_sels_.size());
    std::unordered_set<int> to_deactivate;

    for (int l : core_sels_) {
        if (!consequence_) {
            throw std::runtime_error("process_sels: consequence is not set");
        }
        consequence_->wdelta[l] = -minw_;
        if (wght_.at(l) == minw_) {
            garbage_.insert(l);
            consequence_->removed_lits.push_back(l);
        } else {
            wght_[l] -= minw_;
            if (done_ != -1 && levl_ >= 0 && levl_ < static_cast<int>(blop_.size()) && wght_[l] < blop_[levl_]) {
                wstr_[wght_[l]].push_back(l);
                to_deactivate.insert(l);
            }
        }
        rels_.push_back(-l);
    }

    if (!to_deactivate.empty()) {
        std::vector<int> new_sels;
        new_sels.reserve(sels_.size());
        for (int l : sels_) {
            if (to_deactivate.find(l) == to_deactivate.end()) new_sels.push_back(l);
        }
        sels_.swap(new_sels);
        sels_set_.clear();
        sels_set_.insert(sels_.begin(), sels_.end());
    }
}

std::pair<TotTree*, int> CoreTrailSolver::update_sum(int assump) {
    auto it_t = tobj_.find(assump);
    if (it_t == tobj_.end()) {
        throw std::runtime_error("update_sum: missing totalizer object for assumption");
    }
    TotTree* t = it_t->second;

    auto it_b = bnds_.find(assump);
    if (it_b == bnds_.end()) {
        throw std::runtime_error("update_sum: missing bound for assumption");
    }
    int b = it_b->second + 1;

    ClauseSet delta;
    itot_increase(t, delta, static_cast<unsigned>(b), pool_top_);

    auto& clauses = delta.get_clauses();
    for (const auto& cl : clauses) {
        (void)sat_.add_clause(cl);
    }

    return {t, b};
}

void CoreTrailSolver::set_bound(TotTree* tobj, int rhs, std::optional<long> weight, const std::string& totalizer_id) {
    long w = weight.has_value() ? *weight : minw_;

    int lit = -tobj->vars[static_cast<size_t>(rhs)];

    auto ib = bnds_.find(lit);
    if (ib != bnds_.end()) {
        if (ib->second != rhs) throw std::runtime_error("set_bound: inconsistent bound for existing literal");
        if (tobj_[lit] != tobj) throw std::runtime_error("set_bound: inconsistent totalizer object for literal");
        if (lit_to_totalizerid_[lit] != totalizer_id) throw std::runtime_error("set_bound: inconsistent totalizer id");
        if (swgt_.find(lit) == swgt_.end() || swgt_.at(lit) != w) throw std::runtime_error("set_bound: inconsistent split weight");
        if (wght_.find(lit) == wght_.end()) throw std::runtime_error("set_bound: reactivating dead bound layer");
    } else {
        tobj_[lit] = tobj;
        bnds_[lit] = rhs;
        lit_to_totalizerid_[lit] = totalizer_id;
        set_weight(lit, w);
        swgt_[lit] = w;

        if (consequence_) {
            consequence_->wdelta[lit] = w;
            consequence_->created_sum_deltas.push_back(lit);
        }
    }

    if (!contains_lit(sums_, lit)) {
        sums_.push_back(lit);
        if (consequence_) consequence_->added_lits.push_back(lit);
    }
}

void CoreTrailSolver::process_sums() {
    std::unordered_set<int> to_deactivate;
    for (int l : core_sums_) {
        if (!consequence_) {
            throw std::runtime_error("process_sums: consequence is not set");
        }

        consequence_->wdelta[l] = -minw_;
        if (wght_.at(l) == minw_) {
            garbage_.insert(l);
            consequence_->removed_lits.push_back(l);
        } else {
            wght_[l] -= minw_;
            if (done_ != -1 && levl_ >= 0 && levl_ < static_cast<int>(blop_.size()) && wght_[l] < blop_[levl_]) {
                wstr_[wght_[l]].push_back(l);
                to_deactivate.insert(l);
            }
        }

        auto [t, b] = update_sum(l);

        if (b < static_cast<int>(t->vars.size())) {
            int lnew = -t->vars[static_cast<size_t>(b)];
            if (swgt_.find(lnew) == swgt_.end()) {
                auto it_tid = lit_to_totalizerid_.find(l);
                if (it_tid == lit_to_totalizerid_.end()) {
                    throw std::runtime_error("process_sums: missing totalizer id for core sum assumption");
                }
                set_bound(t, b, swgt_.at(l), it_tid->second);
            }
        }

        rels_.push_back(-l);
    }

    if (!to_deactivate.empty()) {
        std::vector<int> new_sums;
        new_sums.reserve(sums_.size());
        for (int l : sums_) {
            if (to_deactivate.find(l) == to_deactivate.end()) new_sums.push_back(l);
        }
        sums_.swap(new_sums);
    }
}

std::pair<TotTree*, std::string> CoreTrailSolver::create_sum() {
    const int bound = 1;
    ClauseSet delta;
    auto result = itot_dag_.build_counter(
        rels_,
        static_cast<unsigned>(bound),
        exploit_overlap_ ? DAG_OVERLAP_EXPLOIT : DAG_OVERLAP_NONE,
        pool_top_,
        pending_clauses_,
        delta
    );
    TotTree* t = result.root;
    if (t == nullptr) {
        throw std::runtime_error("create_sum: empty totalizer");
    }

    std::string totalizer_id = lits_key(result.rels_used);

    auto& encoded = sum_to_rels_[totalizer_id];
    encoded.clear();
    for (int used_rel : result.rels_used) {
        auto expanded = itot_dag_.expand_rel(used_rel);
        for (int r : expanded) {
            if (!contains_lit(core_sums_, -r)) {
                encoded.insert(r);
                continue;
            }
            auto it_prev = lit_to_totalizerid_.find(-r);
            if (it_prev == lit_to_totalizerid_.end()) {
                throw std::runtime_error("create_sum: missing totalizer id for reused sum literal");
            }
            const auto& existing_rels = sum_to_rels_[it_prev->second];
            encoded.insert(existing_rels.begin(), existing_rels.end());
        }
    }

    auto& clauses = delta.get_clauses();
    for (const auto& cl : clauses) {
        (void)sat_.add_clause(cl);
    }
    return {t, totalizer_id};
}

bool CoreTrailSolver::exhaust_core(TotTree* tobj, const std::string& totalizer_id) {
    set_bound(tobj, 1, std::nullopt, totalizer_id);
    std::vector<int> base = assumptions_;
    append_all(&base, impossible_lits_);

    for (int b = 1; b <= static_cast<int>(rels_.size()) - 1; ++b) {
        int lit = -tobj->vars[static_cast<size_t>(b)];

        std::vector<int> q;
        q.reserve(base.size() + 1U);
        q.push_back(lit);
        append_all(&q, base);
        dedup_lits_inplace(&q);

        if (sat_.solve(q)) {
            set_bound(tobj, b, std::nullopt, totalizer_id);
            filter_assumps();
            consequence_ = nullptr;
            return true;
        }
        if (stop_or_interrupted(true)) {
            // The current probe has not committed a new MaxSAT
            // transformation.  Keep the already encoded relaxation and let
            // ordinary OLL continue on the next call.
            return true;
        }

        cost_ += minw_;

        if (!get_core(true)) {
            throw std::logic_error("core extraction cannot stop after a completed exhaustion SAT call");
        }
        consequence_ = new_consequence(minw_);

        process_sums();
        filter_assumps();
    }

    if (consequence_) {
        for (int relv : rels_) {
            impossible_lits_.push_back(relv);
            consequence_->added_lits.push_back(relv);
        }
    } else {
        for (int relv : rels_) {
            impossible_lits_.push_back(relv);
        }
    }

    consequence_ = nullptr;
    return true;
}

bool CoreTrailSolver::process_core() {
    consequence_ = new_consequence();
    cost_ += minw_;

    garbage_.clear();

    if (core_sels_.size() != 1U || !core_sums_.empty()) {
        process_sels();
        process_sums();

        if (rels_.size() > 1U) {
            std::unordered_set<int> uniq(rels_.begin(), rels_.end());
            if (uniq.size() != rels_.size()) {
                throw std::runtime_error("process_core: duplicate relaxation literals in non-unit core");
            }

            if (rels_.size() == 2U && rels_[0] == -rels_[1]) {
                if (core_.size() != 2U || core_[0] != -core_[1]) {
                    throw std::runtime_error("process_core: complementary rels from non-complementary core");
                }

                filter_assumps();
                return true;
            }

            auto [t, totalizer_id] = create_sum();

            if (!exhaust_) {
                int b = 1;
                set_bound(t, b, minw_, totalizer_id);
            } else {
                if (!exhaust_core(t, totalizer_id)) return false;
            }
        }
    } else {
        impossible_lits_.push_back(-core_sels_[0]);
        if (consequence_) {
            consequence_->added_lits.push_back(-core_sels_[0]);
            consequence_->removed_lits.push_back(core_sels_[0]);
            consequence_->wdelta[core_sels_[0]] = -minw_;
        }
        garbage_.insert(core_sels_[0]);
    }

    filter_assumps();
    return true;
}

bool CoreTrailSolver::compute_(bool run_pre) {
    int i = 0;
    ensure_backend_synced();
    if (stop_or_interrupted()) return false;

    if (run_pre) {
        long max_updated_weight = disable_old_consequences();
        (void)max_updated_weight;

        for (const auto& kv : transition_weights_) {
            int l = kv.first;
            long w = kv.second;
            if (w == 0) {
                erase_weight(l);
                sels_.erase(std::remove(sels_.begin(), sels_.end(), l), sels_.end());
                sels_set_.erase(l);
                sums_.erase(std::remove(sums_.begin(), sums_.end(), l), sums_.end());
                original_wght_[l] = 0;
                all_sels_.insert(l);
                continue;
            }
            if (!contains_lit(sels_, l)) {
                sels_.push_back(l);
                sels_set_.insert(l);
            }
            set_weight(l, w);
            original_wght_[l] = w;
            all_sels_.insert(l);
        }
        transition_weights_.clear();
        normalize_active_objective_assumptions();

        if (!remove_contradictory_objective_assumptions()) return false;

        i = 1;
        ensure_backend_synced();
        if (!remove_contradictory_objective_assumptions()) return false;

        std::vector<int> boot_assumps;
        boot_assumps.reserve(assumptions_.size() + impossible_lits_.size());
        append_all(&boot_assumps, assumptions_);
        append_all(&boot_assumps, impossible_lits_);
        dedup_lits_inplace(&boot_assumps);

        if (!sat_.solve(boot_assumps)) {
            if (stop_or_interrupted(true)) return false;
            return false;
        }
        publish_candidate();
        if (stop_or_interrupted(true)) return false;
    }

    if (adapt_) {
        if (!preprocess_unit_cores_from_base()) return false;
        if (!adapt_am1()) return false;
    }

    bool is_sat = redo_conflicting_assumptions();
    if (stop_or_interrupted()) return false;
    if (!is_sat) {
        return false;
    }

    i += 1;

    while (true) {
        if (stop_or_interrupted()) return false;
        if (!remove_contradictory_objective_assumptions()) return false;
        std::vector<int> loop_assumps;
        loop_assumps.reserve(assumptions_.size() + sels_.size() + sums_.size() + impossible_lits_.size());
        append_all(&loop_assumps, assumptions_);
        append_all(&loop_assumps, sels_);
        append_all(&loop_assumps, sums_);
        append_all(&loop_assumps, impossible_lits_);
        dedup_lits_inplace(&loop_assumps);

        if (sat_.solve(loop_assumps)) {
            publish_candidate();
            if (stop_or_interrupted(true)) return false;
            return true;
        }
        if (stop_or_interrupted(true)) return false;

        i += 1;
        (void)i;

        if (!get_core(false)) return false;
        if (core_.empty()) {
            return false;
        }

        if (!process_core()) return false;
    }
}

bool CoreTrailSolver::compute_base(const std::vector<int>& assumptions) {
    if (stop_or_interrupted()) return false;
    assumptions_.clear();
    assumptions_.reserve(assumptions.size());
    for (int a : assumptions) {
        assumptions_.push_back(map_extlit(a));
    }
    dedup_lits_inplace(&assumptions_);

    neg_ass_.clear();
    neg_ass_.reserve(assumptions_.size());
    for (int l : assumptions_) neg_ass_.push_back(-l);

    bool res = compute_(true);

    last_assumptions_ = assumptions_;
    if (interrupted_last_solve_) {
        return false;
    }
    if (res) {
        model_ = sat_.get_model();

        if (model_.empty() && pool_top_ == 0) {
            model_.clear();
        }

        std::vector<int> mapped;
        mapped.reserve(model_.size());
        model_set_.clear();

        for (int l : model_) {
            int av = std::abs(l);
            auto it = i2e_.find(av);
            if (it == i2e_.end()) continue;
            int ext = l > 0 ? it->second : -it->second;
            mapped.push_back(ext);
            model_set_.insert(ext);
        }

        std::sort(mapped.begin(), mapped.end(), [](int a, int b) { return std::abs(a) < std::abs(b); });

        int vmax = 0;
        for (const auto& kv : e2i_) {
            if (kv.first > vmax) vmax = kv.first;
        }

        std::unordered_set<int> present;
        present.reserve(mapped.size() * 2U + 1U);
        for (int l : mapped) present.insert(std::abs(l));
        for (int v = 1; v <= vmax; ++v) {
            if (present.find(v) == present.end()) {
                mapped.push_back(v);
                model_set_.insert(v);
            }
        }
        std::sort(mapped.begin(), mapped.end(), [](int a, int b) { return std::abs(a) < std::abs(b); });

        model_ = std::move(mapped);
        optimization_complete_ = true;
        terminal_status_ = SolveStatus::OPTIMUM;
        status_ = SolveStatus::OPTIMUM;
        return true;
    }

    model_.clear();
    model_set_.clear();
    optimization_complete_ = true;
    terminal_status_ = SolveStatus::UNSAT;
    status_ = SolveStatus::UNSAT;
    return false;
}

bool CoreTrailSolver::begin_optimization(const std::vector<int>& assumptions) {
    if (stop_or_interrupted()) return false;
    num_calls_ += 1;
    if (num_calls_ > 1 && !full_stratified_) {
        disable_strat_forever();
        return compute_base(assumptions);
    }

    assumptions_.clear();
    assumptions_.reserve(assumptions.size());
    for (int a : assumptions) assumptions_.push_back(map_extlit(a));
    dedup_lits_inplace(&assumptions_);

    neg_ass_.clear();
    neg_ass_.reserve(assumptions_.size());
    for (int l : assumptions_) neg_ass_.push_back(-l);

    long max_updated_weight = disable_old_consequences();

    for (const auto& kv : transition_weights_) {
        int l = kv.first;
        long w = kv.second;
        if (w == 0) {
            erase_weight(l);
            sels_.erase(std::remove(sels_.begin(), sels_.end(), l), sels_.end());
            sels_set_.erase(l);
            sums_.erase(std::remove(sums_.begin(), sums_.end(), l), sums_.end());
            original_wght_[l] = 0;
            continue;
        }
        if (!contains_lit(sels_, l)) {
            sels_.push_back(l);
            sels_set_.insert(l);
        }
        set_weight(l, w);
        original_wght_[l] = w;
    }
    transition_weights_.clear();
    normalize_active_objective_assumptions();

    if (!remove_contradictory_objective_assumptions()) return false;

    {
        ensure_backend_synced();
        std::vector<int> boot = assumptions_;
        append_all(&boot, impossible_lits_);
        dedup_lits_inplace(&boot);
        if (!sat_.solve(boot)) {
            if (stop_or_interrupted(true)) {
                last_assumptions_ = assumptions_;
                model_.clear();
                model_set_.clear();
                return false;
            }
            last_assumptions_ = assumptions_;
            model_.clear();
            model_set_.clear();
            optimization_complete_ = true;
            terminal_status_ = SolveStatus::UNSAT;
            status_ = SolveStatus::UNSAT;
            return false;
        }
        publish_candidate();
    }

    init_wstr();
    sels_.clear();
    sels_set_.clear();
    sums_.clear();
    levl_ = 0;

    if (max_updated_weight > 0) {
        for (int i = 0; i < static_cast<int>(blop_.size()); ++i) {
            if (blop_[i] <= max_updated_weight) {
                levl_ = i;
                break;
            }
        }
    }

    optimization_started_ = true;
    return continue_optimization();
}

bool CoreTrailSolver::continue_optimization() {
    if (!optimization_started_) {
        throw std::logic_error("continue_optimization without an active CoreTrail session");
    }
    if (optimization_complete_) {
        if (terminal_status_ == SolveStatus::OPTIMUM) restore_incumbent();
        status_ = terminal_status_;
        return terminal_status_ == SolveStatus::OPTIMUM;
    }

    if (done_ == 0 && levl_ != -1) {
        next_level();
    }

    if (done_ != -1 && levl_ != -1) {
        while (levl_ != -1 && (level_active_ || done_ < static_cast<int>(blop_.size()))) {
            if (!level_active_) {
                done_ = activate_clauses(done_);
                level_active_ = true;
            }
            if (!remove_contradictory_objective_assumptions()) {
                last_assumptions_ = assumptions_;
                return false;
            }

            if (!compute_(false)) {
                last_assumptions_ = assumptions_;
                if (interrupted_last_solve_) {
                    return false;
                }
                model_.clear();
                model_set_.clear();
                optimization_complete_ = true;
                terminal_status_ = SolveStatus::UNSAT;
                status_ = SolveStatus::UNSAT;
                return false;
            }
            if (stop_or_interrupted()) {
                last_assumptions_ = assumptions_;
                return false;
            }

            level_active_ = false;
            blop_.clear();
            for (const auto& kv : wstr_) blop_.push_back(kv.first);
            std::sort(blop_.begin(), blop_.end(), std::greater<long>());

            if (done_ < static_cast<int>(blop_.size())) {
                if (hard_) finish_level();
                levl_ += 1;
                next_level();
            }
        }
    } else if (done_ == -1) {
        throw std::runtime_error("Enumeration not tested in stratified RC2");
    }

    for (int l : sels_) {
        auto iw = wght_.find(l);
        if (iw == wght_.end() || iw->second <= 0) {
            throw std::runtime_error("All soft clauses should be active at end of stratified compute");
        }
    }
    for (int l : sums_) {
        auto iw = wght_.find(l);
        if (iw == wght_.end() || iw->second <= 0) {
            throw std::runtime_error("All soft clauses should be active at end of stratified compute");
        }
    }
    for (int l : wght_order_) {
        auto it = wght_.find(l);
        if (it == wght_.end()) continue;
        if (it->second <= 0) throw std::runtime_error("All weights should be positive at end of stratified compute");
        if (!contains_lit(sels_, l) && !contains_lit(sums_, l)) {
            throw std::runtime_error("All weights should correspond to active soft clauses at end of stratified compute");
        }
    }

    model_ = sat_.get_model();
    if (model_.empty() && pool_top_ == 0) model_.clear();

    std::vector<int> mapped;
    mapped.reserve(model_.size());
    model_set_.clear();
    for (int l : model_) {
        int av = std::abs(l);
        auto it = i2e_.find(av);
        if (it == i2e_.end()) continue;
        int ext = l > 0 ? it->second : -it->second;
        mapped.push_back(ext);
        model_set_.insert(ext);
    }
    std::sort(mapped.begin(), mapped.end(), [](int a, int b) { return std::abs(a) < std::abs(b); });

    int vmax = 0;
    for (const auto& kv : e2i_) vmax = std::max(vmax, kv.first);
    std::unordered_set<int> present;
    for (int l : mapped) present.insert(std::abs(l));
    for (int v = 1; v <= vmax; ++v) {
        if (present.find(v) == present.end()) {
            mapped.push_back(v);
            model_set_.insert(v);
        }
    }
    std::sort(mapped.begin(), mapped.end(), [](int a, int b) { return std::abs(a) < std::abs(b); });

    model_ = std::move(mapped);
    optimization_complete_ = true;
    terminal_status_ = SolveStatus::OPTIMUM;
    status_ = SolveStatus::OPTIMUM;
    last_assumptions_ = assumptions_;
    return true;
}

bool CoreTrailSolver::compute(const std::vector<int>& assumptions) {
    if (optimization_complete_) {
        if (terminal_status_ == SolveStatus::OPTIMUM) restore_incumbent();
        status_ = terminal_status_;
        return terminal_status_ == SolveStatus::OPTIMUM;
    }
    if (stop_or_interrupted()) return false;
    if (optimization_started_) return continue_optimization();
    return begin_optimization(assumptions);
}

void CoreTrailSolver::add_hard_clause(const std::vector<int>& clause) {
    ensure_open("add_hard_clause");
    std::vector<int> mapped;
    mapped.reserve(clause.size());
    for (int l : clause) {
        if (l == 0) {
            throw std::invalid_argument("0 cannot be in clause");
        }
        mapped.push_back(map_extlit(l));
    }
    pending_clauses_.push_back(std::move(mapped));
    mark_query_dirty();
}

void CoreTrailSolver::add_clause(const std::vector<int>& clause, std::optional<long> weight) {
    ensure_open("add_clause");
    for (int l : clause) {
        if (l == 0) {
            throw std::invalid_argument("0 cannot be in clause");
        }
    }

    if (!weight.has_value() || *weight == 0) {
        add_hard_clause(clause);
        return;
    }
    if (clause.empty()) {
        throw std::invalid_argument("soft clause cannot be empty");
    }

    std::vector<int> mapped;
    mapped.reserve(clause.size());
    for (int l : clause) {
        mapped.push_back(map_extlit(l));
    }

    int selv = mapped.front();
    const std::vector<int> objective_clause = clause;
    if (mapped.size() > 1) {
        selv = ++pool_top_;
        s2cl_[selv] = mapped;
        mapped.push_back(-selv);
        pending_clauses_.push_back(std::move(mapped));
        objective_.add_clause(selv, objective_clause, *weight);
    } else {
        objective_.add_unit(clause.front(), *weight);
    }

    if (all_sels_.find(selv) != all_sels_.end()) {
        // WCNF may contain repeated unit soft clauses. They represent distinct
        // objective terms, so combine their weights on the shared literal.
        // Incremental replacement remains the responsibility of set_soft().
        if (mapped.size() != 1U) {
            throw std::invalid_argument("selector already exists");
        }
        const long previous = original_wght_.at(selv);
        const long combined = previous + *weight;
        set_weight(selv, combined);
        original_wght_[selv] = combined;
        mark_query_dirty();
        return;
    }

    sels_.push_back(selv);
    sall_.push_back(selv);
    sels_set_.insert(selv);
    all_sels_.insert(selv);
    set_weight(selv, *weight);
    original_wght_[selv] = *weight;
    smap_[selv] = static_cast<int>(sels_.size()) - 1;
    mark_query_dirty();
}

void CoreTrailSolver::set_soft(int lit, long weight) {
    ensure_open("set_soft");
    if (weight < 0) {
        throw std::invalid_argument("weight must be positive");
    }
    int lint = map_extlit(lit);
    if (all_sels_.find(lint) != all_sels_.end()) {
        auto it = original_wght_.find(lint);
        long ow = (it == original_wght_.end()) ? 0 : it->second;
        if (weight == ow) {
            transition_weights_.erase(lint);
        } else {
            transition_weights_[lint] = weight;
        }
        objective_.set_unit(lit, weight);
        if (weight != ow) mark_query_dirty();
        return;
    }
    if (weight == 0) return;
    add_clause({lit}, weight);
}

void CoreTrailSolver::add_soft_unit(int lit, long weight) {
    ensure_open("add_soft_unit");
    set_soft(lit, weight);
}

bool CoreTrailSolver::solve(
    const std::vector<int>& assumptions,
    bool raise_on_abnormal,
    std::optional<double> time_limit
) {
    ensure_open("solve");
    if (time_limit.has_value() && (!std::isfinite(*time_limit) || *time_limit <= 0.0)) {
        throw std::invalid_argument("time_limit must be a finite positive number of seconds");
    }
    const std::vector<int> requested_assumptions = canonical_assumptions(assumptions);
    if (!has_active_query_ || requested_assumptions != query_assumptions_) {
        query_assumptions_ = requested_assumptions;
        has_active_query_ = true;
        mark_query_dirty();
    }
    if (query_dirty_) {
        incumbent_cost_.reset();
        incumbent_model_.clear();
        query_dirty_ = false;
    }
    interrupted_last_solve_ = false;
    clear_stop_request();
    if (time_limit.has_value()) {
        sat_.set_time_limit(*time_limit);
    }
    bool sat = false;
    try {
        sat = compute(requested_assumptions);
        if (optimization_complete_) {
            sat_.clear_time_limit();
            return sat;
        }
        const bool interrupted = stop_or_interrupted(true);
        sat_.clear_time_limit();
        if (interrupted) return false;
    } catch (...) {
        sat_.clear_time_limit();
        throw;
    }
    if (!sat && raise_on_abnormal) {
        if (!(status_ == SolveStatus::UNSAT || status_ == SolveStatus::OPTIMUM)) {
            throw std::runtime_error("Abnormal solve status");
        }
    }
    return sat;
}

void CoreTrailSolver::request_stop() noexcept {
    stop_requested_.store(true, std::memory_order_relaxed);
    sat_.interrupt();
}

void CoreTrailSolver::clear_stop_request() noexcept {
    stop_requested_.store(false, std::memory_order_relaxed);
    sat_.clear_interrupt();
}

void CoreTrailSolver::set_interrupt_probe(GlucoseBackend::InterruptProbe probe) noexcept {
    interrupt_probe_ = probe;
    sat_.set_interrupt_probe(probe);
}

bool CoreTrailSolver::stop_requested() const noexcept {
    return stop_requested_.load(std::memory_order_relaxed);
}

bool CoreTrailSolver::interrupted_last_solve() const noexcept {
    return interrupted_last_solve_;
}

SolveStatus CoreTrailSolver::get_status() const noexcept {
    return status_;
}

long CoreTrailSolver::get_cost() const {
    if (!(status_ == SolveStatus::INTERRUPTED_SAT || status_ == SolveStatus::OPTIMUM)) {
        throw std::runtime_error("Objective not available; last status is not SAT/OPTIMUM");
    }
    if (!incumbent_cost_.has_value()) {
        throw std::runtime_error("No exact objective is available");
    }
    return *incumbent_cost_;
}

int CoreTrailSolver::val(int lit) const {
    if (!(status_ == SolveStatus::INTERRUPTED_SAT || status_ == SolveStatus::OPTIMUM)) {
        throw std::runtime_error("No model available");
    }
    if (model_set_.find(lit) != model_set_.end()) return 1;
    if (model_set_.find(-lit) != model_set_.end()) return -1;
    return 0;
}

std::vector<int> CoreTrailSolver::get_model() const {
    if (!(status_ == SolveStatus::INTERRUPTED_SAT || status_ == SolveStatus::OPTIMUM)) {
        throw std::runtime_error("No model available");
    }
    return model_;
}

std::string CoreTrailSolver::signature() const {
    return "core-trail";
}

void CoreTrailSolver::close() noexcept {
    stop_requested_.store(false, std::memory_order_relaxed);
    interrupted_last_solve_ = false;
    query_dirty_ = true;
    has_active_query_ = false;
    query_assumptions_.clear();
    optimization_started_ = false;
    optimization_complete_ = false;
    terminal_status_ = SolveStatus::UNKNOWN;
    level_active_ = false;
    status_ = SolveStatus::UNKNOWN;
    model_.clear();
    model_set_.clear();
    last_assumptions_.clear();
    core_history_.clear();
    am1_sel_cache_.clear();
    blop_.clear();
    wstr_.clear();
    done_ = 0;
    levl_ = 0;
    sels_.clear();
    smap_.clear();
    sall_.clear();
    s2cl_.clear();
    sneg_.clear();
    pool_top_ = 0;
    wght_.clear();
    wght_order_.clear();
    original_wght_.clear();
    objective_.clear();
    incumbent_cost_.reset();
    incumbent_model_.clear();
    all_sels_.clear();
    transition_weights_.clear();
    sums_.clear();
    bnds_.clear();
    bnds_history_.clear();
    tobj_.clear();
    swgt_.clear();
    sum_to_rels_.clear();
    consequence_ = nullptr;
    itot_dag_.clear();
    impossible_lits_.clear();
    lit_to_totalizerid_.clear();
    lit_to_consequence_ = ConsequenceMap();
    cost_ = 0;
    assumptions_.clear();
    neg_ass_.clear();
    sels_ass_.clear();
    sels_impossible_.clear();
    e2i_.clear();
    i2e_.clear();
    fix_nv_.reset();
    minw_ = 0;
    original_core_.clear();
    core_.clear();
    core_sels_.clear();
    core_sums_.clear();
    rels_.clear();
    garbage_.clear();
    sels_set_.clear();
    pending_clauses_.clear();
    sat_.reset();
    closed_ = true;
}

}  // namespace coretrail
