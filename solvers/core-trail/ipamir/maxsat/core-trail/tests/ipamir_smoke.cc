#include <cstdint>
#include <iostream>
#include <limits>

#include "ipamir.h"

namespace {

bool expect(bool condition, const char* message) {
    if (condition) return true;
    std::cerr << "FAIL: " << message << '\n';
    return false;
}

}  // namespace

int main() {
    void* solver = ipamir_init();
    if (!expect(solver != nullptr, "ipamir_init returned null")) return 1;

    // IPAMIR charges a soft literal when it is true. Hardening x therefore
    // makes the soft literal x contribute its full weight.
    ipamir_add_hard(solver, 1);
    ipamir_add_hard(solver, 0);
    ipamir_add_soft_lit(solver, 1, 7);
    if (!expect(ipamir_solve(solver) == 30, "first solve was not optimal")) return 1;
    if (!expect(ipamir_val_obj(solver) == 7, "soft-literal polarity is wrong")) return 1;
    if (!expect(ipamir_val_lit(solver, 1) == 1, "model does not satisfy hard x")) return 1;

    // Assumptions apply to one solve only. This contradiction is UNSAT, while
    // the following solve must restore the prior optimal state.
    ipamir_assume(solver, -1);
    if (!expect(ipamir_solve(solver) == 20, "contradictory assumption was not UNSAT")) return 1;
    if (!expect(ipamir_solve(solver) == 30, "assumption leaked into next solve")) return 1;
    if (!expect(ipamir_val_obj(solver) == 7, "objective changed after assumption reset")) return 1;

    ipamir_release(solver);

    solver = ipamir_init();
    if (!expect(solver != nullptr, "second ipamir_init returned null")) return 1;
    ipamir_add_hard(solver, 0);
    const int empty_status = ipamir_solve(solver);
    if (empty_status != 20) {
        std::cerr << "FAIL: empty hard clause returned " << empty_status << " instead of UNSAT\n";
        return 1;
    }
    ipamir_release(solver);

    solver = ipamir_init();
    if (!expect(solver != nullptr, "third ipamir_init returned null")) return 1;
    ipamir_add_soft_lit(solver, 1, std::numeric_limits<std::uint64_t>::max());
    if (!expect(ipamir_solve(solver) == 40, "out-of-range weight did not enter ERROR")) return 1;
    ipamir_release(solver);
    return 0;
}
