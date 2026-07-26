#include <iostream>
#include <string>
#include <vector>

#include "coretrail/glucose_backend.hpp"

namespace {

bool report(const std::string& name, bool passed, const std::string& detail) {
    std::cout << (passed ? "PASS" : "FAIL") << " " << name << ": " << detail << '\n';
    return passed;
}

}  // namespace

int main() {
    using coretrail::GlucoseBackend;
    using coretrail::SatResult;

    bool all_passed = true;

    {
        GlucoseBackend solver;
        // Each pair needs a decision. This avoids a unit-propagation-only
        // formula that can finish before Glucose reaches a budget check.
        for (int var = 1; var <= 1024; ++var) {
            const int left = 2 * var - 1;
            const int right = 2 * var;
            solver.add_clause({left, right});
            solver.add_clause({-left, -right});
        }
        solver.set_time_limit(1e-12);
        const bool first_result = solver.solve({});
        const bool interrupted = !first_result && solver.get_last_status() == SatResult::UNKNOWN;
        all_passed &= report(
            "deadline interruption",
            interrupted,
            "result=" + std::to_string(first_result) +
                " status=" + std::to_string(static_cast<int>(solver.get_last_status()))
        );

        // A detected deadline is sticky. A second solve must not get a fresh
        // polling window until the caller explicitly clears the deadline.
        const bool remains_interrupted =
            !solver.solve({}) && solver.get_last_status() == SatResult::UNKNOWN;
        all_passed &= report(
            "deadline remains latched",
            remains_interrupted,
            "a detected deadline cannot be forgotten by a polling counter"
        );

        solver.clear_time_limit();
        solver.clear_interrupt();
        const bool resumed = solver.solve({}) && solver.get_last_status() == SatResult::SAT;
        all_passed &= report(
            "deadline resume",
            resumed,
            "the same Glucose instance proves the previously interrupted formula SAT"
        );
    }

    {
        GlucoseBackend solver;
        solver.add_clause({1});
        solver.interrupt();
        const bool first_result = solver.solve({});
        const bool interrupted = !first_result && solver.get_last_status() == SatResult::UNKNOWN;
        all_passed &= report(
            "external interruption",
            interrupted,
            "an explicit interrupt returns UNKNOWN without making the instance inconsistent"
        );

        solver.clear_interrupt();
        const bool resumed = solver.solve({}) && solver.get_last_status() == SatResult::SAT;
        all_passed &= report(
            "external resume",
            resumed,
            "clearing the interrupt lets the same instance continue to SAT"
        );
    }

    {
        GlucoseBackend solver;
        solver.add_clause({1});
        solver.add_clause({-1});
        const bool unsat = !solver.solve({}) && solver.get_last_status() == SatResult::UNSAT;
        all_passed &= report(
            "persistent contradiction",
            unsat,
            "a real hard contradiction remains UNSAT and is distinct from interruption"
        );
    }

    std::cout << "\nGlucose reuse summary: " << (all_passed ? "PASS" : "FAIL") << '\n';
    return all_passed ? 0 : 1;
}
