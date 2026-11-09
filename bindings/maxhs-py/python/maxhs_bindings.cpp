#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <optional>
#include <vector>
#include <new>
#include <stdexcept>
#include <exception>
#include "../maxhs_native.h"
typedef struct {
    PyObject_HEAD MaxHSWrapperNative *native;
} PyMaxHS;
static PyTypeObject Type = {PyVarObject_HEAD_INIT(nullptr, 0)};
static void tr() {
    try {
        throw;
    } catch (const std::bad_alloc &) {
        PyErr_NoMemory();
    } catch (const std::invalid_argument &e) {
        PyErr_SetString(PyExc_ValueError, e.what());
    } catch (const std::exception &e) {
        PyErr_SetString(PyExc_RuntimeError, e.what());
    } catch (...) {
        PyErr_SetString(PyExc_RuntimeError, "Unknown C++ exception");
    }
}
static PyObject *create(PyTypeObject *t, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {nullptr};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "", const_cast<char **>(names)))
        return nullptr;
    auto *s = (PyMaxHS *)t->tp_alloc(t, 0);
    if (!s)
        return nullptr;
    s->native = nullptr;
    try {
        s->native = new MaxHSWrapperNative();
    } catch (...) {
        Py_DECREF((PyObject *)s);
        tr();
        return nullptr;
    }
    return (PyObject *)s;
}
static void destroy(PyMaxHS *s) {
    delete s->native;
    s->native = nullptr;
    Py_TYPE(s)->tp_free((PyObject *)s);
}
static PyObject *newVar(PyMaxHS *s, PyObject *) {
    try {
        return PyLong_FromLong(s->native->newVar());
    } catch (...) {
        tr();
        return nullptr;
    }
}
static PyObject *setN(PyMaxHS *s, PyObject *o) {
    long n = PyLong_AsLong(o);
    if (n == -1 && PyErr_Occurred())
        return nullptr;
    if (n <= INT_MIN || n > INT_MAX) {
        PyErr_SetString(PyExc_OverflowError, "variable count out of range");
        return nullptr;
    }
    s->native->setNInputVars((int)n);
    Py_RETURN_NONE;
}
static PyObject *add(PyMaxHS *s, PyObject *a, PyObject *k) {
    static const char *n[] = {"clause", "weight", nullptr};
    PyObject *c, *w = Py_None;
    if (!PyArg_ParseTupleAndKeywords(a, k, "O|O:addClause", (char **)n, &c, &w))
        return nullptr;
    PyObject *q = PySequence_Fast(c, "clause must be iterable");
    if (!q)
        return nullptr;
    std::vector<int> v;
    try {
        auto z = PySequence_Fast_GET_SIZE(q);
        v.reserve(z);
        for (Py_ssize_t i = 0; i < z; ++i) {
            long x = PyLong_AsLong(PySequence_Fast_GET_ITEM(q, i));
            if (x == -1 && PyErr_Occurred()) {
                Py_DECREF(q);
                return nullptr;
            }
            if (!x || x <= INT_MIN || x > INT_MAX) {
                Py_DECREF(q);
                PyErr_SetString(!x ? PyExc_ValueError : PyExc_OverflowError, "invalid literal");
                return nullptr;
            }
            v.push_back((int)x);
        }
        Py_DECREF(q);
        q = nullptr;
        std::optional<long long> weight;
        if (w != Py_None) {
            long long z = PyLong_AsLongLong(w);
            if (z == -1 && PyErr_Occurred())
                return nullptr;
            weight = z;
        }
        s->native->addClause(v, weight);
        Py_RETURN_NONE;
    } catch (...) {
        Py_XDECREF(q);
        tr();
        return nullptr;
    }
}
static PyObject *solve(PyMaxHS *s, PyObject *) {
    try {
        bool r = false;
        std::exception_ptr e;
        Py_BEGIN_ALLOW_THREADS try { r = s->native->solve(); } catch (...) {
            e = std::current_exception();
        }
        Py_END_ALLOW_THREADS if (e) std::rethrow_exception(e);
        return PyBool_FromLong(r);
    } catch (...) {
        tr();
        return nullptr;
    }
}
static PyObject *status(PyMaxHS *s, PyObject *) { return PyLong_FromLong(s->native->status()); }
static PyObject *cost(PyMaxHS *s, PyObject *) {
    try {
        return PyLong_FromLongLong(s->native->cost());
    } catch (...) {
        tr();
        return nullptr;
    }
}
static PyObject *model(PyMaxHS *s, PyObject *) {
    try {
        auto v = s->native->model();
        PyObject *l = PyList_New(v.size());
        if (!l)
            return nullptr;
        for (size_t i = 0; i < v.size(); ++i)
            PyList_SET_ITEM(l, i, PyLong_FromLong(v[i]));
        return l;
    } catch (...) {
        tr();
        return nullptr;
    }
}
static PyMethodDef methods[] = {
    {"newVar", (PyCFunction)newVar, METH_NOARGS, nullptr},
    {"setNInputVars", (PyCFunction)setN, METH_O, nullptr},
    {"addClause", (PyCFunction)(void (*)(void))add, METH_VARARGS | METH_KEYWORDS, nullptr},
    {"solve", (PyCFunction)solve, METH_NOARGS, nullptr},
    {"solve_status", (PyCFunction)status, METH_NOARGS, nullptr},
    {"getCost", (PyCFunction)cost, METH_NOARGS, nullptr},
    {"getModel", (PyCFunction)model, METH_NOARGS, nullptr},
    {nullptr, nullptr, 0, nullptr}};
static PyModuleDef module = {PyModuleDef_HEAD_INIT, "maxhs_py", "MaxHS native binding", -1,
                             nullptr};
PyMODINIT_FUNC PyInit_maxhs_py() {
    Type.tp_name = "maxhs_py.MaxHS";
    Type.tp_basicsize = sizeof(PyMaxHS);
    Type.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    Type.tp_new = create;
    Type.tp_dealloc = (destructor)destroy;
    Type.tp_methods = methods;
    if (PyType_Ready(&Type) < 0)
        return nullptr;
    PyObject *m = PyModule_Create(&module);
    if (!m)
        return nullptr;
    Py_INCREF(&Type);
    if (PyModule_AddObject(m, "MaxHS", (PyObject *)&Type) < 0) {
        Py_DECREF(&Type);
        Py_DECREF(m);
        return nullptr;
    }
    return m;
}
