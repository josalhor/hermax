#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <cstdint>
#include <vector>
#include <stdexcept>
#include <new>
#include <exception>
#include "tt_openwbo_native.h"

typedef struct {
    PyObject_HEAD TTOpenWBOIncNative *native;
} PyTTOpenWBOInc;
static PyTypeObject TTType = {PyVarObject_HEAD_INIT(nullptr, 0)};
static void tt_translate() {
    try {
        throw;
    } catch (const std::bad_alloc &) {
        PyErr_NoMemory();
    } catch (const std::invalid_argument &e) {
        PyErr_SetString(PyExc_ValueError, e.what());
    } catch (const std::overflow_error &e) {
        PyErr_SetString(PyExc_OverflowError, e.what());
    } catch (const std::exception &e) {
        PyErr_SetString(PyExc_RuntimeError, e.what());
    } catch (...) {
        if (!PyErr_Occurred())
            PyErr_SetString(PyExc_RuntimeError, "Unknown C++ exception");
    }
}
static PyObject *tt_new(PyTypeObject *t, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {nullptr};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "", const_cast<char **>(names)))
        return nullptr;
    auto *s = (PyTTOpenWBOInc *)t->tp_alloc(t, 0);
    if (!s)
        return nullptr;
    s->native = nullptr;
    try {
        s->native = new TTOpenWBOIncNative();
    } catch (...) {
        Py_DECREF((PyObject *)s);
        tt_translate();
        return nullptr;
    }
    return (PyObject *)s;
}
static void tt_dealloc(PyTTOpenWBOInc *s) {
    delete s->native;
    s->native = nullptr;
    Py_TYPE(s)->tp_free((PyObject *)s);
}
static PyObject *tt_newvar(PyTTOpenWBOInc *s, PyObject *) {
    try {
        return PyLong_FromLong(s->native->new_var());
    } catch (...) {
        tt_translate();
        return nullptr;
    }
}
static PyObject *tt_add(PyTTOpenWBOInc *s, PyObject *args, PyObject *kw) {
    static const char *n[] = {"clause", "weight", nullptr};
    PyObject *c, *w = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kw, "O|O:addClause", (char **)n, &c, &w))
        return nullptr;
    PyObject *q = PySequence_Fast(c, "clause must be iterable");
    if (!q)
        return nullptr;
    std::vector<int> v;
    try {
        auto z = PySequence_Fast_GET_SIZE(q);
        v.reserve((size_t)z);
        for (Py_ssize_t i = 0; i < z; ++i) {
            long x = PyLong_AsLong(PySequence_Fast_GET_ITEM(q, i));
            if (x == -1 && PyErr_Occurred()) {
                Py_DECREF(q);
                return nullptr;
            }
            if (!x || x <= INT_MIN || x > INT_MAX) {
                Py_DECREF(q);
                PyErr_SetString(x == 0 ? PyExc_ValueError : PyExc_OverflowError, "invalid literal");
                return nullptr;
            }
            v.push_back((int)x);
        }
        Py_DECREF(q);
        long long weight = 0;
        bool soft = w != Py_None;
        if (soft) {
            weight = PyLong_AsLongLong(w);
            if (weight == -1 && PyErr_Occurred())
                return nullptr;
            if (weight <= 0) {
                PyErr_SetString(PyExc_ValueError, "soft weight must be positive");
                return nullptr;
            }
        }
        s->native->add_clause(v, soft, weight);
        Py_RETURN_NONE;
    } catch (...) {
        Py_DECREF(q);
        tt_translate();
        return nullptr;
    }
}
static PyObject *tt_solve(PyTTOpenWBOInc *s, PyObject *) {
    try {
        bool r = false;
        std::exception_ptr e;
        Py_BEGIN_ALLOW_THREADS try { r = s->native->solve(); } catch (...) {
            e = std::current_exception();
        }
        Py_END_ALLOW_THREADS if (e) std::rethrow_exception(e);
        return PyBool_FromLong(r);
    } catch (...) {
        tt_translate();
        return nullptr;
    }
}
static PyObject *tt_cost(PyTTOpenWBOInc *s, PyObject *) {
    try {
        return PyLong_FromUnsignedLongLong(s->native->cost());
    } catch (...) {
        tt_translate();
        return nullptr;
    }
}
static PyObject *tt_value(PyTTOpenWBOInc *s, PyObject *o) {
    long x = PyLong_AsLong(o);
    if (x == -1 && PyErr_Occurred())
        return nullptr;
    if (x <= INT_MIN || x > INT_MAX) {
        PyErr_SetString(PyExc_OverflowError, "variable out of range");
        return nullptr;
    }
    try {
        return PyBool_FromLong(s->native->value((int)x));
    } catch (...) {
        tt_translate();
        return nullptr;
    }
}
static PyMethodDef tt_methods[] = {
    {"newVar", (PyCFunction)tt_newvar, METH_NOARGS, nullptr},
    {"addClause", (PyCFunction)(void (*)(void))tt_add, METH_VARARGS | METH_KEYWORDS, nullptr},
    {"solve", (PyCFunction)tt_solve, METH_NOARGS, nullptr},
    {"getCost", (PyCFunction)tt_cost, METH_NOARGS, nullptr},
    {"getValue", (PyCFunction)tt_value, METH_O, nullptr},
    {nullptr, nullptr, 0, nullptr}};
static PyModuleDef tt_module = {PyModuleDef_HEAD_INIT, "tt_openwbo_inc",
                                "TT-Open-WBO-Inc native binding", -1, nullptr};
PyMODINIT_FUNC PyInit_tt_openwbo_inc() {
    TTType.tp_name = "tt_openwbo_inc.TTOpenWBOInc";
    TTType.tp_basicsize = sizeof(PyTTOpenWBOInc);
    TTType.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    TTType.tp_new = tt_new;
    TTType.tp_dealloc = (destructor)tt_dealloc;
    TTType.tp_methods = tt_methods;
    if (PyType_Ready(&TTType) < 0)
        return nullptr;
    PyObject *m = PyModule_Create(&tt_module);
    if (!m)
        return nullptr;
    Py_INCREF(&TTType);
    if (PyModule_AddObject(m, "TTOpenWBOInc", (PyObject *)&TTType) < 0) {
        Py_DECREF(&TTType);
        Py_DECREF(m);
        return nullptr;
    }
    return m;
}
