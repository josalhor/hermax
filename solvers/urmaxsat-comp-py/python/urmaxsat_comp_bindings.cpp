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
#include "../ipamir.h"
struct CallbackState {
    PyObject *callback;
};
typedef struct {
    PyObject_HEAD void *solver;
    PyObject *callback;
    CallbackState cbstate;
    int num_vars;
} PyUWrComp;
static PyTypeObject UWrCompType = {PyVarObject_HEAD_INIT(nullptr, 0)};
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
static int callback(void *state) {
    auto *cb = static_cast<CallbackState *>(state);
    if (!cb || !cb->callback)
        return 0;
    PyObject *r = PyObject_CallNoArgs(cb->callback);
    int out = 0;
    if (!r) {
        PyErr_WriteUnraisable(cb->callback);
        out = 1;
    } else {
        long v = PyLong_AsLong(r);
        if (v == -1 && PyErr_Occurred()) {
            PyErr_WriteUnraisable(cb->callback);
            out = 1;
        } else
            out = (int)v;
        Py_DECREF(r);
    }
    return out;
}
static void release(PyUWrComp *s) {
    if (s->solver) {
        ipamir_release(s->solver);
        s->solver = nullptr;
    }
}
static void ensure(PyUWrComp *s) {
    if (!s->solver)
        throw std::runtime_error("UWrMaxSAT native state is released.");
}
static PyObject *construct(PyTypeObject *t, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {nullptr};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "", const_cast<char **>(names)))
        return nullptr;
    auto *s = (PyUWrComp *)t->tp_alloc(t, 0);
    if (!s)
        return nullptr;
    s->solver = nullptr;
    s->callback = nullptr;
    s->cbstate.callback = nullptr;
    s->num_vars = 0;
    try {
        s->solver = ipamir_init();
        if (!s->solver)
            throw std::runtime_error("Failed to initialize UWrMaxSAT 1.4 solver.");
    } catch (...) {
        Py_DECREF((PyObject *)s);
        translate();
        return nullptr;
    }
    return (PyObject *)s;
}
static void dealloc(PyUWrComp *s) {
    release(s);
    Py_XDECREF(s->callback);
    s->callback = nullptr;
    Py_TYPE(s)->tp_free((PyObject *)s);
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
            if (x <= std::numeric_limits<int>::min() || x > std::numeric_limits<int>::max() || !x ||
                x == INT_MIN) {
                Py_DECREF(q);
                PyErr_SetString(!x ? PyExc_ValueError : PyExc_OverflowError, "invalid literal");
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
static PyObject *newvar(PyUWrComp *s, PyObject *) {
    try {
        ensure(s);
        return PyLong_FromLong(++s->num_vars);
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *addclause(PyUWrComp *s, PyObject *args, PyObject *kw) {
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
            maxv = std::max(maxv, std::abs(lit));
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
static PyObject *assume(PyUWrComp *s, PyObject *o) {
    std::vector<int> v;
    if (ints(o, v, "assumptions must be an iterable of integers") < 0)
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
static PyObject *solve(PyUWrComp *s, PyObject *) {
    try {
        ensure(s);
    } catch (...) {
        translate();
        return nullptr;
    }
    int result = 0;
    try {
        result = ipamir_solve(s->solver);
    } catch (...) {
        translate();
        return nullptr;
    }
    return PyLong_FromLong(result);
}
static PyObject *cost(PyUWrComp *s, PyObject *) {
    try {
        ensure(s);
        return PyLong_FromUnsignedLongLong(ipamir_val_obj(s->solver));
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *value(PyUWrComp *s, PyObject *o) {
    long lit = PyLong_AsLong(o);
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
static PyObject *setterm(PyUWrComp *s, PyObject *o) {
    if (o != Py_None && !PyCallable_Check(o)) {
        PyErr_SetString(PyExc_TypeError, "callback must be callable or None");
        return nullptr;
    }
    try {
        ensure(s);
        Py_XINCREF(o == Py_None ? nullptr : o);
        Py_XDECREF(s->callback);
        s->callback = o == Py_None ? nullptr : o;
        s->cbstate.callback = s->callback;
        ipamir_set_terminate(s->solver, s->callback ? &s->cbstate : nullptr,
                             s->callback ? callback : nullptr);
        Py_RETURN_NONE;
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *signature(PyUWrComp *, PyObject *) {
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
static PyModuleDef module = {PyModuleDef_HEAD_INIT, "urmaxsat_comp_py",
                             "UWrMaxSAT 1.4 native binding", -1, methods};
PyMODINIT_FUNC PyInit_urmaxsat_comp_py() {
    UWrCompType.tp_name = "urmaxsat_comp_py.UWrMaxSAT";
    UWrCompType.tp_basicsize = sizeof(PyUWrComp);
    UWrCompType.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    UWrCompType.tp_new = construct;
    UWrCompType.tp_dealloc = (destructor)dealloc;
    UWrCompType.tp_methods = methods;
    if (PyType_Ready(&UWrCompType) < 0)
        return nullptr;
    PyObject *m = PyModule_Create(&module);
    if (!m)
        return nullptr;
    Py_INCREF(&UWrCompType);
    if (PyModule_AddObject(m, "UWrMaxSAT", (PyObject *)&UWrCompType) < 0) {
        Py_DECREF(&UWrCompType);
        Py_DECREF(m);
        return nullptr;
    }
    return m;
}
