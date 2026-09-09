#include <csignal>

#include "hermax_ctrlc_guard.h"

static hermax_ctrlc_guard guard{};
static volatile sig_atomic_t signal_count = 0;

static void count_signal(int, void *) {
    ++signal_count;
}

static void old_handler(int) {
    ++signal_count;
}

static int run_guarded_call() {
    const hermax_ctrlc_guard_config config{count_signal, nullptr};
    const int entered = hermax_ctrlc_guard_enter(&guard, &config);
    if (entered == HERMAX_CTRLC_ENTERED) {
        std::raise(SIGINT);
        return 10;
    }
    if (entered == HERMAX_CTRLC_INTERRUPTED) {
        hermax_ctrlc_guard_leave(&guard);
        return 0;
    }
    return 11;
}

int main() {
    std::signal(SIGINT, old_handler);
    if (run_guarded_call() != 0 || signal_count != 1) {
        return 1;
    }

    std::raise(SIGINT);
    return signal_count == 2 ? 0 : 2;
}
