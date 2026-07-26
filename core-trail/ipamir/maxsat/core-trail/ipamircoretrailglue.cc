#include <cstdint>
#include <exception>
#include <limits>
#include <string>
#include <vector>
#include <jemalloc/jemalloc.h>

#include "../../ipamir.h"
#include "coretrail/coretrail_solver.hpp"

namespace {

struct SolverHandle {
    coretrail::CoreTrailSolver solver;
    std::vector<int> hard_clause;
    std::vector<int> assumptions;
    bool has_empty_hard_clause{false};
    std::string input_error{};

    void* term_state{nullptr};
    int (*term_cb)(void*){nullptr};

    explicit SolverHandle()
        : solver(coretrail::CoreTrailOptions{}) {
    }
};

static inline SolverHandle* as_handle(void* p) {
    return reinterpret_cast<SolverHandle*>(p);
}

}  // namespace

extern "C" {

const char* ipamir_signature() {
    return "core-trail";
}

void* ipamir_init() {
    try {
        uint64_t epoch = 1;
        size_t sz = sizeof(epoch);
        if (mallctl("epoch", &epoch, &sz, &epoch, sz) != 0) {
            return nullptr;
        }
        return new SolverHandle();
    } catch (...) {
        return nullptr;
    }
}

void ipamir_release(void* solver) {
    delete as_handle(solver);
}

void ipamir_add_hard(void* solver, int32_t lit_or_zero) {
    auto* h = as_handle(solver);
    if (!h || !h->input_error.empty()) return;

    try {
        if (lit_or_zero == 0) {
            if (h->hard_clause.empty()) {
                h->has_empty_hard_clause = true;
                return;
            }
            h->solver.add_hard_clause(h->hard_clause);
            h->hard_clause.clear();
            return;
        }
        h->hard_clause.push_back(static_cast<int>(lit_or_zero));
    } catch (const std::exception& error) {
        h->input_error = error.what();
    }
}

void ipamir_add_soft_lit(void* solver, int32_t lit, uint64_t weight) {
    auto* h = as_handle(solver);
    if (!h || !h->input_error.empty()) return;
    if (lit == 0) return;
    if (weight > static_cast<uint64_t>(std::numeric_limits<long>::max())) {
        h->input_error = "soft weight exceeds CoreTrail's signed weight range";
        return;
    }
    try {
        h->solver.set_soft(-static_cast<int>(lit), static_cast<long>(weight));
    } catch (const std::exception& error) {
        h->input_error = error.what();
    }
}

void ipamir_assume(void* solver, int32_t lit) {
    auto* h = as_handle(solver);
    if (!h) return;
    if (lit == 0) return;

    h->assumptions.push_back((int)lit);
}

int ipamir_solve(void* solver) {
    auto* h = as_handle(solver);
    if (!h) return 40;

    try {
        if (!h->input_error.empty()) {
            h->assumptions.clear();
            return 40;
        }
        if (h->has_empty_hard_clause) {
            h->assumptions.clear();
            return 20;
        }
        if (h->term_cb && h->term_cb(h->term_state)) {
            h->assumptions.clear();
            return 0;
        }

        (void)h->solver.solve(h->assumptions, false);
        h->assumptions.clear();

        switch (h->solver.get_status()) {
            case coretrail::SolveStatus::INTERRUPTED:
                return 0;
            case coretrail::SolveStatus::INTERRUPTED_SAT:
                return 10;
            case coretrail::SolveStatus::UNSAT:
                return 20;
            case coretrail::SolveStatus::OPTIMUM:
                return 30;
            case coretrail::SolveStatus::ERROR:
                return 40;
            case coretrail::SolveStatus::UNKNOWN:
            default:
                return 0;
        }
    } catch (...) {
        h->assumptions.clear();
        return 40;
    }
}

uint64_t ipamir_val_obj(void* solver) {
    auto* h = as_handle(solver);
    if (!h) return 0;

    try {
        long c = h->solver.get_cost();
        return c < 0 ? 0 : (uint64_t)c;
    } catch (...) {
        return 0;
    }
}

int32_t ipamir_val_lit(void* solver, int32_t lit) {
    auto* h = as_handle(solver);
    if (!h || lit == 0) return 0;

    try {
        int v = h->solver.val((int)lit);
        if (v > 0) return lit;
        if (v < 0) return -lit;
        return 0;
    } catch (...) {
        return 0;
    }
}

void ipamir_set_terminate(void* solver, void* state, int (*terminate)(void*)) {
    auto* h = as_handle(solver);
    if (!h) return;
    h->term_state = state;
    h->term_cb = terminate;
}

}  // extern "C"
