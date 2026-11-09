#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "../nuwls_native.h"
#include <exception>
#include <limits>
#include <new>
#include <stdexcept>
#include <vector>
typedef struct {
    PyObject_HEAD nuwls_native::Solver *solver;
} PySolver;
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
        PyErr_SetString(PyExc_RuntimeError, "Unknown C++ exception");
    }
}
static PyObject *create(PyTypeObject *t) {
    auto *s = reinterpret_cast<PySolver *>(t->tp_alloc(t, 0));
    if (!s)
        return nullptr;
    s->solver = nullptr;
    try {
        s->solver = new nuwls_native::Solver();
    } catch (...) {
        Py_DECREF(reinterpret_cast<PyObject *>(s));
        translate();
        return nullptr;
    }
    return reinterpret_cast<PyObject *>(s);
}
static PyObject *construct(PyTypeObject *t, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {nullptr};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "", const_cast<char **>(names)))
        return nullptr;
    return create(t);
}
static void destroy(PySolver *s) {
    delete s->solver;
    s->solver = nullptr;
    Py_TYPE(s)->tp_free(reinterpret_cast<PyObject *>(s));
}
static int ints(PyObject *o, std::vector<int> &v, const char *m) {
    PyObject *q = PySequence_Fast(o, m);
    if (!q)
        return -1;
    Py_ssize_t n = PySequence_Fast_GET_SIZE(q);
    try {
        v.reserve(n);
        for (Py_ssize_t i = 0; i < n; ++i) {
            long x = PyLong_AsLong(PySequence_Fast_GET_ITEM(q, i));
            if (x == -1 && PyErr_Occurred()) {
                Py_DECREF(q);
                return -1;
            }
            if (x <= INT32_MIN || x > INT32_MAX) {
                Py_DECREF(q);
                PyErr_SetString(PyExc_OverflowError, "literal does not fit in C int");
                return -1;
            }
            v.push_back(static_cast<int>(x));
        }
    } catch (...) {
        Py_DECREF(q);
        translate();
        return -1;
    }
    Py_DECREF(q);
    return 0;
}
static PyObject *newvar(PySolver *s, PyObject *) {
    try {
        return PyLong_FromLong(s->solver->new_var());
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *setvars(PySolver *s, PyObject *o) {
    unsigned long n = PyLong_AsUnsignedLong(o);
    if (n == (unsigned long)-1 && PyErr_Occurred())
        return nullptr;
    if (n > UINT32_MAX) {
        PyErr_SetString(PyExc_OverflowError, "n does not fit in unsigned int");
        return nullptr;
    }
    try {
        s->solver->set_n_input_vars((unsigned)n);
        Py_RETURN_NONE;
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *addclause(PySolver *s, PyObject *a, PyObject *k) {
    static const char *names[] = {"clause", "weight", nullptr};
    PyObject *c, *w = Py_None;
    if (!PyArg_ParseTupleAndKeywords(a, k, "O|O:addClause", const_cast<char **>(names), &c, &w))
        return nullptr;
    std::vector<int> l;
    if (ints(c, l, "clause must be an iterable of integers") < 0)
        return nullptr;
    bool has = w != Py_None;
    long long weight = 0;
    if (has) {
        weight = PyLong_AsLongLong(w);
        if (weight == -1 && PyErr_Occurred())
            return nullptr;
    }
    try {
        s->solver->add_clause(l, has, weight);
        Py_RETURN_NONE;
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *solve(PySolver *s, PyObject *a, PyObject *k) {
    static const char *names[] = {"assumptions", nullptr};
    PyObject *o = Py_None;
    if (!PyArg_ParseTupleAndKeywords(a, k, "|O:solve", const_cast<char **>(names), &o))
        return nullptr;
    std::vector<int> v;
    if (o != Py_None && ints(o, v, "assumptions must be an iterable of integers") < 0)
        return nullptr;
    bool result = false;
    std::exception_ptr error;
    Py_BEGIN_ALLOW_THREADS try { result = s->solver->solve(v, o != Py_None); } catch (...) {
        error = std::current_exception();
    }
    Py_END_ALLOW_THREADS if (error) {
        try {
            std::rethrow_exception(error);
        } catch (...) {
            translate();
            return nullptr;
        }
    }
    return PyBool_FromLong(result);
}
static PyObject *cost(PySolver *s, PyObject *) {
    try {
        return PyLong_FromUnsignedLongLong(s->solver->get_cost());
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *value(PySolver *s, PyObject *o) {
    long v = PyLong_AsLong(o);
    if (v == -1 && PyErr_Occurred())
        return nullptr;
    if (v <= INT32_MIN || v > INT32_MAX) {
        PyErr_SetString(PyExc_OverflowError, "variable does not fit in C int");
        return nullptr;
    }
    try {
        return PyBool_FromLong(s->solver->get_value((int)v));
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *model(PySolver *s, PyObject *) {
    try {
        auto v = s->solver->get_model();
        PyObject *l = PyList_New(v.size());
        if (!l)
            return nullptr;
        for (size_t i = 0; i < v.size(); ++i) {
            PyObject *x = PyLong_FromLong(v[i]);
            if (!x) {
                Py_DECREF(l);
                return nullptr;
            }
            PyList_SET_ITEM(l, i, x);
        }
        return l;
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyObject *status(PySolver *s, PyObject *) {
    try {
        return PyLong_FromLong(s->solver->get_status());
    } catch (...) {
        translate();
        return nullptr;
    }
}
static PyMethodDef methods[] = {
    {"getStatus", (PyCFunction)status, METH_NOARGS, nullptr},
    {"newVar", (PyCFunction)newvar, METH_NOARGS, nullptr},
    {"setNInputVars", (PyCFunction)setvars, METH_O, nullptr},
    {"addClause", (PyCFunction)(void (*)(void))addclause, METH_VARARGS | METH_KEYWORDS, nullptr},
    {"solve", (PyCFunction)(void (*)(void))solve, METH_VARARGS | METH_KEYWORDS, nullptr},
    {"getCost", (PyCFunction)cost, METH_NOARGS, nullptr},
    {"getValue", (PyCFunction)value, METH_O, nullptr},
    {"getModel", (PyCFunction)model, METH_NOARGS, nullptr},
    {nullptr, nullptr, 0, nullptr}};
static PyModuleDef module = {PyModuleDef_HEAD_INIT, "nuwls_c_ibr",
                             "NuWLS-c-IBR BLS native bindings", -1, nullptr};
PyMODINIT_FUNC PyInit_nuwls_c_ibr() {
    SolverType.tp_name = "nuwls_c_ibr.NuWLSCIBR";
    SolverType.tp_basicsize = sizeof(PySolver);
    SolverType.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    SolverType.tp_new = construct;
    SolverType.tp_dealloc = (destructor)destroy;
    SolverType.tp_methods = methods;
    if (PyType_Ready(&SolverType) < 0)
        return nullptr;
    PyObject *m = PyModule_Create(&module);
    if (!m)
        return nullptr;
    Py_INCREF(&SolverType);
    if (PyModule_AddObject(m, "NuWLSCIBR", (PyObject *)&SolverType) < 0) {
        Py_DECREF(&SolverType);
        Py_DECREF(m);
        return nullptr;
    }
    return m;
}
