#pragma once

#include <cstdint>
#include <deque>
#include <memory>
#include <optional>
#include <atomic>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "coretrail/glucose_backend.hpp"
#include "coretrail/objective_store.hpp"
#include "dag.hh"

struct TotTree;

namespace coretrail {

// The counter encoder remains vendored under its historical namespace.
using rc2::DAG_OVERLAP_EXPLOIT;
using rc2::DAG_OVERLAP_NONE;
using rc2::ItotDag;

enum class SolveStatus : int {
    INTERRUPTED = 0,
    INTERRUPTED_SAT = 10,
    UNSAT = 20,
    OPTIMUM = 30,
    ERROR = 40,
    UNKNOWN = 60,
};

struct Consequence {
    int counter{0};
    long weight{0};
    bool is_clique{false};
    std::vector<int> removed_lits{};
    std::vector<int> added_lits{};
    std::vector<int> core{};
    std::unordered_map<int, long> wdelta{};
    std::vector<int> created_sum_deltas{};
};

class ConsequenceMap {
public:
    void add(int lit, const std::shared_ptr<Consequence>& c);
    void remove(int consequence_counter);
    void bulk_remove(const std::vector<int>& counters);
    std::shared_ptr<Consequence> new_consequence(long weight, const std::vector<int>& core);
    const std::vector<std::shared_ptr<Consequence>>* get(int lit) const;
    std::vector<std::shared_ptr<Consequence>> all() const;

private:
    std::unordered_map<int, std::vector<std::shared_ptr<Consequence>>> map_{};
    std::unordered_map<int, std::vector<int>> inverse_{};
    int counter_{0};
};

struct CoreTrailOptions {
    std::string solver{"g4"};
    bool adapt{true};
    std::string blo{"div"};
    bool exhaust{false};
    bool incr{false};
    bool minz{true};
    bool nohard{true};
    bool core_memory{false};
    int core_replay{10};
    bool full_stratified{true};
    bool exploit_overlap{false};
    int trim{0};
    int verbose{0};
};

struct CoreSplit {
    std::vector<int> sels_ass{};
    std::vector<int> reduced_core{};
    std::vector<int> impossible_soft{};
};

class CoreTrailSolver {
public:
    explicit CoreTrailSolver(CoreTrailOptions opts = {});
    ~CoreTrailSolver() = default;

    // Formula loading and incremental interface
    void initialize_external_vars(int nv);
    void add_hard_clause(const std::vector<int>& clause);
    void add_clause(const std::vector<int>& clause, std::optional<long> weight = std::nullopt);
    void set_soft(int lit, long weight);
    void add_soft_unit(int lit, long weight);

    // Solve API
    bool solve(
        const std::vector<int>& assumptions = {},
        bool raise_on_abnormal = false,
        std::optional<double> time_limit = std::nullopt
    );
    void request_stop() noexcept;
    void clear_stop_request() noexcept;
    void set_interrupt_probe(GlucoseBackend::InterruptProbe probe) noexcept;
    bool stop_requested() const noexcept;
    bool interrupted_last_solve() const noexcept;
    SolveStatus get_status() const noexcept;
    long get_cost() const;
    int val(int lit) const;
    std::vector<int> get_model() const;
    std::string signature() const;
    void close() noexcept;

private:
    [[noreturn]] void not_impl(const char* fn) const;
    void ensure_open(const char* fn) const;
    void set_weight(int lit, long weight);
    void erase_weight(int lit);

    // Query-1 helpers and base loop skeleton
    int map_extlit(int lit);
    CoreSplit split_core_assumptions(const std::vector<int>& core) const;
    void filter_assumps();
    std::shared_ptr<Consequence> new_consequence(std::optional<long> weight = std::nullopt);
    bool compute_base(const std::vector<int>& assumptions);
    bool compute(const std::vector<int>& assumptions);
    bool compute_(bool run_pre = true);
    bool begin_optimization(const std::vector<int>& assumptions);
    bool continue_optimization();
    void init_wstr();
    void next_level();
    int activate_clauses(int beg);
    void finish_level();
    void disable_strat_forever();

    // Invocation points kept intact; some are placeholders for later queries.
    long disable_old_consequences();
    bool redo_conflicting_assumptions();
    bool preprocess_unit_cores_from_base();
    bool adapt_am1();
    int am1_get_or_create_selector(const std::vector<int>& clique);
    void process_am1(std::vector<int> am1);
    bool get_core(bool skip_heuristics = false);
    bool process_core();
    void handle_core(bool remember);
    void process_sels();
    void process_sums();
    void normalize_active_objective_assumptions();
    bool remove_contradictory_objective_assumptions();
    bool is_active_objective_lit(int l) const;
    std::pair<TotTree*, std::string> create_sum();
    std::pair<TotTree*, int> update_sum(int assump);
    void set_bound(TotTree* tobj, int rhs, std::optional<long> weight = std::nullopt, const std::string& totalizer_id = "");
    bool exhaust_core(TotTree* tobj, const std::string& totalizer_id);
    bool trim_core();
    bool minimize_core();

    void ensure_backend_synced();
    std::vector<int> canonical_assumptions(const std::vector<int>& assumptions) const;
    void mark_query_dirty() noexcept;
    bool stop_or_interrupted(bool check_sat_unknown = false);
    void publish_candidate();
    void restore_incumbent();

private:
    CoreTrailOptions opts_{};

    // RC2_IX2.__init__ persistent state (1:1 intent)
    long num_calls_{0};
    int verbose_{0};
    bool exhaust_{false};
    std::string solver_name_{"g4"};
    bool adapt_{false};
    bool minz_{false};
    int trim_{0};
    SolveStatus status_{SolveStatus::UNKNOWN};
    bool core_memory_{false};
    int core_replay_{0};
    std::vector<int> last_assumptions_{};
    std::deque<std::vector<std::vector<int>>> core_history_{};
    std::vector<int> model_{};
    std::unordered_set<int> model_set_{};
    std::unordered_map<std::string, int> am1_sel_cache_{};
    int levl_{0};
    std::vector<long> blop_{};
    bool full_stratified_{true};
    bool exploit_overlap_{false};
    int bstr_{0};
    bool hard_{false};
    std::unordered_map<long, std::vector<int>> wstr_{};
    double sdiv_{0.0};
    int done_{0};

    // selectors and mappings
    std::vector<int> sels_{};
    std::unordered_map<int, int> smap_{};
    std::vector<int> sall_{};
    std::unordered_map<int, std::vector<int>> s2cl_{};
    std::unordered_set<int> sneg_{};
    // MaxSAT working state
    int pool_top_{0};
    std::unordered_map<int, long> wght_{};
    std::vector<int> wght_order_{};
    std::unordered_map<int, long> original_wght_{};
    ObjectiveStore objective_{};
    std::optional<long> incumbent_cost_{};
    std::vector<int> incumbent_model_{};
    std::unordered_set<int> all_sels_{};
    std::unordered_map<int, long> transition_weights_{};
    std::vector<int> sums_{};
    std::unordered_map<int, int> bnds_{};
    std::unordered_map<int, int> bnds_history_{};
    std::unordered_map<int, TotTree*> tobj_{};
    std::unordered_map<int, long> swgt_{};
    std::unordered_map<std::string, std::unordered_set<int>> sum_to_rels_{};
    std::shared_ptr<Consequence> consequence_{nullptr};
    std::vector<int> impossible_lits_{};
    std::unordered_map<int, std::string> lit_to_totalizerid_{};
    ConsequenceMap lit_to_consequence_{};
    ItotDag itot_dag_{};
    long cost_{0};

    // assumptions-related state
    std::vector<int> assumptions_{};
    std::vector<int> neg_ass_{};
    std::vector<int> sels_ass_{};
    std::vector<int> sels_impossible_{};

    // variable mapping
    std::unordered_map<int, int> e2i_{};
    std::unordered_map<int, int> i2e_{};

    // init tail field
    std::optional<int> fix_nv_{};

    // core working fields
    long minw_{0};
    std::vector<int> original_core_{};
    std::vector<int> core_{};
    std::vector<int> core_sels_{};
    std::vector<int> core_sums_{};
    std::vector<int> rels_{};
    std::unordered_set<int> garbage_{};
    std::unordered_set<int> sels_set_{};

    // SAT backend state
    // Clauses produced since the last SAT call. They are inserted once and
    // then released; CoreTrail never rebuilds an already-live SAT backend.
    std::vector<std::vector<int>> pending_clauses_{};
    GlucoseBackend sat_{};
    bool closed_{false};
    std::atomic<bool> stop_requested_{false};
    GlucoseBackend::InterruptProbe interrupt_probe_{nullptr};
    bool interrupted_last_solve_{false};
    bool query_dirty_{true};
    bool has_active_query_{false};
    std::vector<int> query_assumptions_{};
    // A session is the CoreTrail search state for one logical query. It is
    // retained across timed calls and invalidated only by a query change.
    bool optimization_started_{false};
    bool optimization_complete_{false};
    SolveStatus terminal_status_{SolveStatus::UNKNOWN};
    bool level_active_{false};
};

}  // namespace coretrail
