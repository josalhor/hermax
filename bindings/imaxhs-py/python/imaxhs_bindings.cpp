#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <cstdint>
#include <limits>
#include <vector>
#include <exception>
#include <new>
#include <stdexcept>
#include <cstdlib>
#include "../../../solvers/incremental-maxhs/src/ipamir/ipamir.h"
struct CallbackState {
    PyObject *callback;
    PyObject *owner;
};
typedef struct {
    PyObject_HEAD void *solver;
    PyObject *callback;
    CallbackState cb;
    PyObject *exc_type;
    PyObject *exc_value;
    PyObject *exc_tb;
    int num_vars;
} PyIMaxHS;
static PyTypeObject SolverType = {PyVarObject_HEAD_INIT(nullptr, 0)};
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
static void release(PyIMaxHS *s) {
    if (s->solver) {
        ipamir_release(s->solver);
        s->solver = nullptr;
    }
}
static void ensure(PyIMaxHS *s) {
    if (!s->solver)
        throw std::runtime_error("Solver is closed.");
}
static void fetch_callback_error(PyIMaxHS *s) {
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
static bool restore_callback_error(PyIMaxHS *s) {
    if (!s->exc_type)
        return false;
    PyErr_Restore(s->exc_type, s->exc_value, s->exc_tb);
    s->exc_type = s->exc_value = s->exc_tb = nullptr;
    return true;
}
static int callback(void *state) {
    auto *c = (CallbackState *)state;
    if (!c)
        return 0;
    PyGILState_STATE g = PyGILState_Ensure();
    if (!c->callback) {
        PyGILState_Release(g);
        return 0;
    }
    PyObject *r = PyObject_CallNoArgs(c->callback);
    int out = 0;
    if (!r) {
        fetch_callback_error((PyIMaxHS *)c->owner);
        out = 1;
    } else {
        long x = PyLong_AsLong(r);
        if (x == -1 && PyErr_Occurred()) {
            fetch_callback_error((PyIMaxHS *)c->owner);
            out = 1;
        } else
            out = (int)x;
        Py_DECREF(r);
    }
    PyGILState_Release(g);
    return out;
}
static PyObject *construct(PyTypeObject *t, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {nullptr};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "", const_cast<char **>(names)))
        return nullptr;
    auto *s = (PyIMaxHS *)t->tp_alloc(t, 0);
    if (!s)
        return nullptr;
    s->solver = nullptr;
    s->callback = nullptr;
    s->cb.callback = nullptr;
    s->cb.owner = (PyObject *)s;
    s->exc_type = s->exc_value = s->exc_tb = nullptr;
    s->num_vars = 0;
    try {
        s->solver = ipamir_init();
        if (!s->solver)
            throw std::runtime_error("Failed to initialize solver.");
    } catch (...) {
        Py_DECREF((PyObject *)s);
        translate();
        return nullptr;
    }
    return (PyObject *)s;
}
static void dealloc(PyIMaxHS *s) {
    release(s);
    Py_XDECREF(s->callback);
    Py_XDECREF(s->exc_type);
    Py_XDECREF(s->exc_value);
    Py_XDECREF(s->exc_tb);
    s->callback = nullptr;
    Py_TYPE(s)->tp_free((PyObject *)s);
}
static int readints(PyObject *o, std::vector<int> &v, const char *msg) {
    PyObject *q = PySequence_Fast(o, msg);
    if (!q)
        return -1;
    try {
        Py_ssize_t n = PySequence_Fast_GET_SIZE(q);
        v.reserve((size_t)n);
        for (Py_ssize_t i = 0; i < n; ++i) {
            long x = PyLong_AsLong(PySequence_Fast_GET_ITEM(q, i));
            if (x == -1 && PyErr_Occurred()) {
                Py_DECREF(q);
                return -1;
            }
            if (!x || x <= INT_MIN || x > INT_MAX) {
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
static PyObject *newvar(PyIMaxHS *s, PyObject *) {
    try {
        ensure(s);
        return PyLong_FromLong(++s->num_vars);
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *addclause(PyIMaxHS *s, PyObject *a, PyObject *k) {
    static const char *n[] = {"clause", "weight", nullptr};
    PyObject *c, *w = Py_None;
    if (!PyArg_ParseTupleAndKeywords(a, k, "O|O:addClause", (char **)n, &c, &w))
        return nullptr;
    std::vector<int> v;
    if (readints(c, v, "clause must be an iterable of integers") < 0)
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
        for (int x : v)
            maxv = std::max(maxv, std::abs(x));
        if (!soft || v.size() != 1) {
            for (int x : v)
                ipamir_add_hard(s->solver, x);
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
static PyObject *assume(PyIMaxHS *s, PyObject *o) {
    std::vector<int> v;
    if (readints(o, v, "assumptions must be iterable") < 0)
        return nullptr;
    try {
        ensure(s);
        for (int x : v)
            ipamir_assume(s->solver, x);
        Py_RETURN_NONE;
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *solve(PyIMaxHS *s, PyObject *) {
    try {
        ensure(s);
        int r = 0;
        std::exception_ptr e;
        Py_BEGIN_ALLOW_THREADS try { r = ipamir_solve(s->solver); } catch (...) {
            e = std::current_exception();
        }
        Py_END_ALLOW_THREADS if (restore_callback_error(s)) return nullptr;
        if (e)
            std::rethrow_exception(e);
        return PyLong_FromLong(r);
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *cost(PyIMaxHS *s, PyObject *) {
    try {
        ensure(s);
        return PyLong_FromUnsignedLongLong(ipamir_val_obj(s->solver));
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *value(PyIMaxHS *s, PyObject *o) {
    long x = PyLong_AsLong(o);
    if (x == -1 && PyErr_Occurred())
        return nullptr;
    if (!x || x <= INT_MIN || x > INT_MAX) {
        PyErr_SetString(PyExc_ValueError, "invalid literal");
        return nullptr;
    }
    try {
        ensure(s);
        int r = ipamir_val_lit(s->solver, (int)x);
        if (r == x)
            Py_RETURN_TRUE;
        if (r == -x)
            Py_RETURN_FALSE;
        Py_RETURN_NONE;
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *setterm(PyIMaxHS *s, PyObject *o) {
    if (o != Py_None && !PyCallable_Check(o)) {
        PyErr_SetString(PyExc_TypeError, "callback must be callable or None");
        return nullptr;
    }
    try {
        ensure(s);
        PyObject *n = o == Py_None ? nullptr : o;
        Py_XINCREF(n);
        Py_XDECREF(s->callback);
        s->callback = n;
        s->cb.callback = n;
        ipamir_set_terminate(s->solver, n ? &s->cb : nullptr, n ? callback : nullptr);
        Py_RETURN_NONE;
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *signature(PyIMaxHS *, PyObject *) {
    return PyUnicode_FromString(ipamir_signature());
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
static PyModuleDef module = {PyModuleDef_HEAD_INIT, "imaxhs_py", "IMaxHS native binding", -1,
                             methods};
PyMODINIT_FUNC PyInit_imaxhs_py() {
    SolverType.tp_name = "imaxhs_py.IMaxHS";
    SolverType.tp_basicsize = sizeof(PyIMaxHS);
    SolverType.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    SolverType.tp_new = construct;
    SolverType.tp_dealloc = (destructor)dealloc;
    SolverType.tp_methods = methods;
    if (PyType_Ready(&SolverType) < 0)
        return nullptr;
    PyObject *m = PyModule_Create(&module);
    if (!m)
        return nullptr;
    Py_INCREF(&SolverType);
    if (PyModule_AddObject(m, "IMaxHS", (PyObject *)&SolverType) < 0) {
        Py_DECREF(&SolverType);
        Py_DECREF(m);
        return nullptr;
    }
    return m;
}
