/*
 * Hermax native Ctrl-C guard, version 1.
 *
 * This is intentionally a small, copyable POSIX header for native solver
 * bindings.  It provides an escape hatch for an already-audited call into a
 * solver which cannot cooperatively stop itself.  The signal handler only
 * records interruption, optionally calls an async-signal-safe callback, and
 * returns control to the guarded binding frame.  Resource release belongs in
 * the normal escaped path, after hermax_ctrlc_guard_leave().
 *
 * Constraints:
 * - one active guard per compiled extension at a time;
 * - callers must pair every successful enter with leave;
 * - the guard itself must outlive the guarded stack frame (for example, keep
 *   it in the binding object, not as a local created immediately before enter);
 * - do not create C++ objects with non-trivial destructors between enter and
 *   the guarded call: siglongjmp intentionally bypasses unwinding;
 * - the optional on_signal callback must be async-signal-safe.
 *
 * On Windows, the same enter/leave API uses a console-control handler.  A
 * configured callback is the cooperative path; without one, Ctrl-C terminates
 * the current process because Windows cannot unwind the solver thread from a
 * console-control handler thread.
 */

#ifndef HERMAX_CTRLC_GUARD_H
#define HERMAX_CTRLC_GUARD_H

#define HERMAX_CTRLC_GUARD_VERSION 1

#if !defined(_WIN32)

#include <errno.h>
#include <setjmp.h>
#include <signal.h>

typedef void (*hermax_ctrlc_on_signal_fn)(int signum, void *state);

typedef struct hermax_ctrlc_guard_config {
    hermax_ctrlc_on_signal_fn on_signal;
    void *state;
} hermax_ctrlc_guard_config;

typedef struct hermax_ctrlc_guard {
    sigjmp_buf jump_buffer;
    struct sigaction previous_action;
    hermax_ctrlc_guard_config config;
    volatile sig_atomic_t active;
    volatile sig_atomic_t interrupted;
} hermax_ctrlc_guard;

enum hermax_ctrlc_enter_result {
    HERMAX_CTRLC_ENTERED = 0,
    HERMAX_CTRLC_INTERRUPTED = 1,
    HERMAX_CTRLC_UNAVAILABLE = -1,
};

/* Each extension receives isolated state.  Cross-extension concurrent native
 * solves are intentionally not supported by this first, process-signal based
 * implementation. */
static hermax_ctrlc_guard *hermax_ctrlc_active_guard = 0;

static void hermax_ctrlc_signal_handler(int signum) {
    hermax_ctrlc_guard *guard = hermax_ctrlc_active_guard;
    if (guard == 0 || !guard->active) {
        return;
    }

    guard->interrupted = 1;
    if (guard->config.on_signal != 0) {
        guard->config.on_signal(signum, guard->config.state);
    }
    siglongjmp(guard->jump_buffer, 1);
}

static int hermax_ctrlc_guard_enter_impl(
    hermax_ctrlc_guard *guard,
    const hermax_ctrlc_guard_config *config,
    int escaped
) {
    if (guard == 0) {
        errno = EINVAL;
        return HERMAX_CTRLC_UNAVAILABLE;
    }

    sigset_t block_sigint;
    sigemptyset(&block_sigint);
    sigaddset(&block_sigint, SIGINT);
    sigset_t saved_mask;
    if (sigprocmask(SIG_BLOCK, &block_sigint, &saved_mask) != 0) {
        return HERMAX_CTRLC_UNAVAILABLE;
    }

    if (escaped != 0) {
        sigprocmask(SIG_SETMASK, &saved_mask, 0);
        return HERMAX_CTRLC_INTERRUPTED;
    }

    if (hermax_ctrlc_active_guard != 0) {
        sigprocmask(SIG_SETMASK, &saved_mask, 0);
        errno = EBUSY;
        return HERMAX_CTRLC_UNAVAILABLE;
    }

    guard->config = config == 0
        ? hermax_ctrlc_guard_config{0, 0}
        : *config;
    guard->interrupted = 0;
    guard->active = 0;

    struct sigaction action;
    action.sa_handler = hermax_ctrlc_signal_handler;
    sigemptyset(&action.sa_mask);
    action.sa_flags = 0;
    if (sigaction(SIGINT, &action, &guard->previous_action) != 0) {
        sigprocmask(SIG_SETMASK, &saved_mask, 0);
        return HERMAX_CTRLC_UNAVAILABLE;
    }

    hermax_ctrlc_active_guard = guard;
    guard->active = 1;
    sigprocmask(SIG_SETMASK, &saved_mask, 0);
    return HERMAX_CTRLC_ENTERED;
}

/* sigsetjmp must execute in the binding frame that will receive siglongjmp;
 * wrapping it in an ordinary function would jump into a returned stack frame. */
#define hermax_ctrlc_guard_enter(guard, config) \
    hermax_ctrlc_guard_enter_impl((guard), (config), sigsetjmp((guard)->jump_buffer, 1))

static void hermax_ctrlc_guard_leave(hermax_ctrlc_guard *guard) {
    if (guard == 0 || !guard->active) {
        return;
    }

    sigset_t block_sigint;
    sigset_t current_mask;
    sigemptyset(&block_sigint);
    sigaddset(&block_sigint, SIGINT);
    if (sigprocmask(SIG_BLOCK, &block_sigint, &current_mask) != 0) {
        return;
    }

    guard->active = 0;
    if (hermax_ctrlc_active_guard == guard) {
        hermax_ctrlc_active_guard = 0;
    }
    sigaction(SIGINT, &guard->previous_action, 0);
    sigprocmask(SIG_SETMASK, &current_mask, 0);
}

#else

#include <windows.h>
#include <signal.h>

typedef void (*hermax_ctrlc_on_signal_fn)(int signum, void *state);

typedef struct hermax_ctrlc_guard_config {
    hermax_ctrlc_on_signal_fn on_signal;
    void *state;
} hermax_ctrlc_guard_config;

typedef struct hermax_ctrlc_guard {
    hermax_ctrlc_guard_config config;
    volatile LONG active;
    volatile LONG interrupted;
} hermax_ctrlc_guard;

enum hermax_ctrlc_enter_result {
    HERMAX_CTRLC_ENTERED = 0,
    HERMAX_CTRLC_INTERRUPTED = 1,
    HERMAX_CTRLC_UNAVAILABLE = -1,
};

static hermax_ctrlc_guard *hermax_ctrlc_active_guard = 0;

static BOOL WINAPI hermax_ctrlc_console_handler(DWORD event_type) {
    if (event_type != CTRL_C_EVENT && event_type != CTRL_BREAK_EVENT) {
        return FALSE;
    }

    hermax_ctrlc_guard *guard = hermax_ctrlc_active_guard;
    if (guard == 0 || InterlockedCompareExchange(&guard->active, 0, 0) == 0) {
        return FALSE;
    }

    InterlockedExchange(&guard->interrupted, 1);
    if (guard->config.on_signal != 0) {
        /* The callback is supplied only by a solver with an audited,
         * thread-safe cooperative cancellation path. */
        guard->config.on_signal(SIGINT, guard->config.state);
        return TRUE;
    }

    /* Console handlers execute on a different thread.  There is no safe
     * equivalent of jumping into the thread currently inside a native solver. */
    TerminateProcess(GetCurrentProcess(), 0xC000013Au);
    return TRUE;
}

static int hermax_ctrlc_guard_enter_impl(
    hermax_ctrlc_guard *guard, const hermax_ctrlc_guard_config *config, int
) {
    if (guard == 0 || hermax_ctrlc_active_guard != 0) {
        return HERMAX_CTRLC_UNAVAILABLE;
    }

    guard->config = config == 0
        ? hermax_ctrlc_guard_config{0, 0}
        : *config;
    InterlockedExchange(&guard->interrupted, 0);
    InterlockedExchange(&guard->active, 1);
    hermax_ctrlc_active_guard = guard;
    if (!SetConsoleCtrlHandler(hermax_ctrlc_console_handler, TRUE)) {
        hermax_ctrlc_active_guard = 0;
        InterlockedExchange(&guard->active, 0);
        return HERMAX_CTRLC_UNAVAILABLE;
    }
    return HERMAX_CTRLC_ENTERED;
}

#define hermax_ctrlc_guard_enter(guard, config) \
    hermax_ctrlc_guard_enter_impl((guard), (config), 0)

static void hermax_ctrlc_guard_leave(hermax_ctrlc_guard *guard) {
    if (guard == 0 || InterlockedCompareExchange(&guard->active, 0, 0) == 0) {
        return;
    }

    InterlockedExchange(&guard->active, 0);
    if (hermax_ctrlc_active_guard == guard) {
        hermax_ctrlc_active_guard = 0;
    }
    SetConsoleCtrlHandler(hermax_ctrlc_console_handler, FALSE);
}

#endif

#endif
