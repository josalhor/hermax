#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <cstdint>
#include <limits>
#include <vector>
#include <string>
#include <exception>
#include <new>
#include <stdexcept>
#include <cstdlib>
#include "../uwrmaxsat/ipamir.h"
#include "hermax_ctrlc_guard.h"
typedef struct {
    PyObject_HEAD void *solver;
    PyObject *callback;
    PyObject *exc_type;
    PyObject *exc_value;
    PyObject *exc_tb;
    int num_vars;
    hermax_ctrlc_guard ctrlc_guard;
} PyUWr;
static PyTypeObject UWrType = {PyVarObject_HEAD_INIT(nullptr, 0)};
static void translate() {
    try {
        throw;
    } catch (const std::invalid_argument &e) {
        PyErr_SetString(PyExc_ValueError, e.what());
    } catch (const std::overflow_error &e) {
        PyErr_SetString(PyExc_OverflowError, e.what());
    } catch (const std::bad_alloc &) {
        PyErr_NoMemory();
    } catch (const std::exception &e) {
        PyErr_SetString(PyExc_RuntimeError, e.what());
    } catch (...) {
        if (!PyErr_Occurred())
            PyErr_SetString(PyExc_RuntimeError, "Unknown C++ exception");
    }
}
static void release_solver(PyUWr *s) {
    if (s->solver) {
        ipamir_release(s->solver);
        s->solver = nullptr;
    }
}
static void fetch_callback_error(PyUWr *s) {
    PyObject *t = nullptr, *v = nullptr, *tb = nullptr;
    PyErr_Fetch(&t, &v, &tb);
    if (!s->exc_type) {
        s->exc_type = t;
        s->exc_value = v;
        s->exc_tb = tb;
    } else {
        Py_XDECREF(t);
        Py_XDECREF(v);
        Py_XDECREF(tb);
    }
}
static bool restore_callback_error(PyUWr *s) {
    if (!s->exc_type)
        return false;
    PyErr_Restore(s->exc_type, s->exc_value, s->exc_tb);
    s->exc_type = s->exc_value = s->exc_tb = nullptr;
    return true;
}
static int callback(void *state) {
    auto *s = (PyUWr *)state;
    if (!s)
        return 0;
    PyGILState_STATE gil = PyGILState_Ensure();
    if (!s->callback) {
        PyGILState_Release(gil);
        return 0;
    }
    PyObject *r = PyObject_CallNoArgs(s->callback);
    int out = 0;
    if (!r) {
        fetch_callback_error(s);
        out = 1;
    } else {
        long v = PyLong_AsLong(r);
        if (v == -1 && PyErr_Occurred()) {
            fetch_callback_error(s);
            out = 1;
        } else
            out = (int)v;
        Py_DECREF(r);
    }
    PyGILState_Release(gil);
    return out;
}
static PyObject *construct(PyTypeObject *t, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {nullptr};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "", const_cast<char **>(names)))
        return nullptr;
    auto *s = (PyUWr *)t->tp_alloc(t, 0);
    if (!s)
        return nullptr;
    s->solver = nullptr;
    s->callback = nullptr;
    s->exc_type = s->exc_value = s->exc_tb = nullptr;
    s->num_vars = 0;
    try {
        s->solver = ipamir_init();
        if (!s->solver)
            throw std::runtime_error("Failed to initialize UWrMaxSAT solver.");
    } catch (...) {
        Py_DECREF((PyObject *)s);
        translate();
        return nullptr;
    }
    return (PyObject *)s;
}
static void dealloc(PyUWr *s) {
    release_solver(s);
    Py_XDECREF(s->callback);
    Py_XDECREF(s->exc_type);
    Py_XDECREF(s->exc_value);
    Py_XDECREF(s->exc_tb);
    s->callback = nullptr;
    Py_TYPE(s)->tp_free((PyObject *)s);
}
static void ensure(PyUWr *s) {
    if (!s->solver)
        throw std::runtime_error("UWrMaxSAT native state was released after Ctrl-C interruption.");
}
static int ints(PyObject *o, std::vector<int> &v, const char *msg) {
    PyObject *q = PySequence_Fast(o, msg);
    if (!q)
        return -1;
    auto n = PySequence_Fast_GET_SIZE(q);
    try {
        v.reserve(n);
        for (Py_ssize_t i = 0; i < n; ++i) {
            long x = PyLong_AsLong(PySequence_Fast_GET_ITEM(q, i));
            if (x == -1 && PyErr_Occurred()) {
                Py_DECREF(q);
                return -1;
            }
            if (x <= std::numeric_limits<int>::min() || x > std::numeric_limits<int>::max() ||
                x == 0 || x == INT_MIN) {
                Py_DECREF(q);
                PyErr_SetString(x == 0 ? PyExc_ValueError : PyExc_OverflowError, "invalid literal");
                return -1;
            }
            v.push_back((int)x);
        }
    } catch (...) {
        Py_DECREF(q);
        translate();
        return -1;
    }
    Py_DECREF(q);
    return 0;
}
static PyObject *newvar(PyUWr *s, PyObject *) {
    try {
        ensure(s);
        return PyLong_FromLong(++s->num_vars);
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *addclause(PyUWr *s, PyObject *args, PyObject *kw) {
    static const char *n[] = {"clause", "weight", nullptr};
    PyObject *c, *w = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kw, "O|O:addClause", (char **)n, &c, &w))
        return nullptr;
    std::vector<int> v;
    if (ints(c, v, "clause must be an iterable of integers") < 0)
        return nullptr;
    bool soft = w != Py_None;
    long long weight = 0;
    if (soft) {
        weight = PyLong_AsLongLong(w);
        if (weight == -1 && PyErr_Occurred())
            return nullptr;
        if (weight <= 0) {
            PyErr_SetString(PyExc_ValueError, "soft weight must be positive");
            return nullptr;
        }
    }
    try {
        ensure(s);
        int maxv = s->num_vars;
        for (int lit : v)
            if (std::abs(lit) > maxv)
                maxv = std::abs(lit);
        if (!soft || v.size() != 1) {
            for (int lit : v)
                ipamir_add_hard(s->solver, lit);
            if (soft) {
                int aux = ++maxv;
                ipamir_add_hard(s->solver, aux);
                ipamir_add_hard(s->solver, 0);
                ipamir_add_soft_lit(s->solver, aux, (uint64_t)weight);
            } else
                ipamir_add_hard(s->solver, 0);
        } else
            ipamir_add_soft_lit(s->solver, -v[0], (uint64_t)weight);
        s->num_vars = maxv;
        Py_RETURN_NONE;
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *assume(PyUWr *s, PyObject *arg) {
    std::vector<int> v;
    if (ints(arg, v, "assumptions must be an iterable of integers") < 0)
        return nullptr;
    try {
        ensure(s);
        for (int lit : v)
            ipamir_assume(s->solver, lit);
        Py_RETURN_NONE;
    } catch (...) {
        translate();
        return nullptr;
    }
}
// The Ctrl-C guard uses longjmp: retain the GIL so interruption cannot
// bypass restoration of Python thread state.
static PyObject *solve(PyUWr *s, PyObject *) {
    try {
        ensure(s);
    } catch (...) {
        translate();
        return nullptr;
    }
    int gr = hermax_ctrlc_guard_enter(&s->ctrlc_guard, nullptr);
    if (gr == HERMAX_CTRLC_ENTERED) {
        int result = 0;
        std::exception_ptr error;
        try {
            result = ipamir_solve(s->solver);
        } catch (...) {
            error = std::current_exception();
        }
        hermax_ctrlc_guard_leave(&s->ctrlc_guard);
        if (restore_callback_error(s))
            return nullptr;
        if (error) {
            try {
                std::rethrow_exception(error);
            } catch (...) {
                translate();
                return nullptr;
            }
        }
        return PyLong_FromLong(result);
    }
    if (gr == HERMAX_CTRLC_INTERRUPTED) {
        hermax_ctrlc_guard_leave(&s->ctrlc_guard);
        release_solver(s);
        PyErr_SetNone(PyExc_KeyboardInterrupt);
        return nullptr;
    }
    int result = 0;
    std::exception_ptr error;
    try {
        result = ipamir_solve(s->solver);
    } catch (...) {
        error = std::current_exception();
    }
    if (restore_callback_error(s))
        return nullptr;
    if (error) {
        try {
            std::rethrow_exception(error);
        } catch (...) {
            translate();
            return nullptr;
        }
    }
    return PyLong_FromLong(result);
}
static PyObject *cost(PyUWr *s, PyObject *) {
    try {
        ensure(s);
        return PyLong_FromUnsignedLongLong(ipamir_val_obj(s->solver));
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *value(PyUWr *s, PyObject *arg) {
    long lit = PyLong_AsLong(arg);
    if (lit == -1 && PyErr_Occurred())
        return nullptr;
    if (lit <= INT_MIN || lit > INT_MAX || !lit) {
        PyErr_SetString(PyExc_ValueError, "invalid literal");
        return nullptr;
    }
    try {
        ensure(s);
        int v = ipamir_val_lit(s->solver, (int)lit);
        if (v == lit)
            Py_RETURN_TRUE;
        if (v == -lit)
            Py_RETURN_FALSE;
        Py_RETURN_NONE;
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *setterm(PyUWr *s, PyObject *arg) {
    if (arg != Py_None && !PyCallable_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "callback must be callable or None");
        return nullptr;
    }
    try {
        ensure(s);
        Py_XINCREF(arg == Py_None ? nullptr : arg);
        Py_XDECREF(s->callback);
        s->callback = arg == Py_None ? nullptr : arg;
        ipamir_set_terminate(s->solver, s->callback ? s : nullptr,
                             s->callback ? callback : nullptr);
        Py_RETURN_NONE;
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *signature(PyUWr *, PyObject *) {
    const char *x = ipamir_signature();
    return PyUnicode_FromString(x ? x : "");
}
static PyMethodDef methods[] = {
    {"newVar", (PyCFunction)newvar, METH_NOARGS, nullptr},
    {"addClause", (PyCFunction)(void (*)(void))addclause, METH_VARARGS | METH_KEYWORDS, nullptr},
    {"assume", (PyCFunction)assume, METH_O, nullptr},
    {"solve", (PyCFunction)solve, METH_NOARGS, nullptr},
    {"getCost", (PyCFunction)cost, METH_NOARGS, nullptr},
    {"getValue", (PyCFunction)value, METH_O, nullptr},
    {"set_terminate", (PyCFunction)setterm, METH_O, nullptr},
    {"signature", (PyCFunction)signature, METH_NOARGS, nullptr},
    {nullptr, nullptr, 0, nullptr}};
static PyModuleDef module = {PyModuleDef_HEAD_INIT, "urmaxsat_py", "UWrMaxSAT native binding", -1,
                             methods};
PyMODINIT_FUNC PyInit_urmaxsat_py() {
    UWrType.tp_name = "urmaxsat_py.UWrMaxSAT";
    UWrType.tp_basicsize = sizeof(PyUWr);
    UWrType.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    UWrType.tp_new = construct;
    UWrType.tp_dealloc = (destructor)dealloc;
    UWrType.tp_methods = methods;
    if (PyType_Ready(&UWrType) < 0)
        return nullptr;
    PyObject *m = PyModule_Create(&module);
    if (!m)
        return nullptr;
    Py_INCREF(&UWrType);
    if (PyModule_AddObject(m, "UWrMaxSAT", (PyObject *)&UWrType) < 0) {
        Py_DECREF(&UWrType);
        Py_DECREF(m);
        return nullptr;
    }
    return m;
}
