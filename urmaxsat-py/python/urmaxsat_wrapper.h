#ifndef URMAXSAT_WRAPPER_H
#define URMAXSAT_WRAPPER_H

#include "ipamir.h"
#include <vector>
#include <stdexcept>

class UWrMaxSat {
public:
    UWrMaxSat() {
        solver = ipamir_init();
        if (solver == nullptr) {
            throw std::runtime_error("Failed to initialize UWrMaxSat solver.");
        }
        vars = 0;
    }

    ~UWrMaxSat() {
        if (solver) {
            ipamir_release(solver);
        }
    }

    int newVar() {
        vars++;
        return vars;
    }

    void addClause(const std::vector<int>& clause, long long weight = -1) {
        if (weight == -1) { // Hard clause
            for (int lit : clause) {
                ipamir_add_hard(solver, lit);
            }
            ipamir_add_hard(solver, 0);
        } else { // Soft clause
            // To add a soft clause (C) with weight w, we need a new variable b
            // and add a hard clause (C or b) and a soft literal (!b) with weight w.
            int b = newVar();
            for (int lit : clause) {
                ipamir_add_hard(solver, lit);
            }
            ipamir_add_hard(solver, b);
            ipamir_add_hard(solver, 0);
            ipamir_add_soft_lit(solver, -b, weight);
        }
    }

    int solve() {
        return ipamir_solve(solver);
    }

    long long getCost() {
        return ipamir_val_obj(solver);
    }

    int getValue(int lit) {
        return ipamir_val_lit(solver, lit);
    }

private:
    void* solver;
    int vars;
};

#endif // URMAXSAT_WRAPPER_H
