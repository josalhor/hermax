#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <cstdint>
#include <limits>
#include <vector>
#include <stdexcept>
#include <new>
#include <exception>

#include "openwbo_inc_native.h"

typedef struct {
    PyObject_HEAD OpenWBOIncNative *native;
} PyOpenWBOInc;
static PyTypeObject OpenWBOIncType = {PyVarObject_HEAD_INIT(nullptr, 0)};
static void translate_openwbo() {
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
static PyObject *ow_new(PyTypeObject *t, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {nullptr};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "", const_cast<char **>(names)))
        return nullptr;
    auto *s = (PyOpenWBOInc *)t->tp_alloc(t, 0);
    if (!s)
        return nullptr;
    s->native = nullptr;
    try {
        s->native = new OpenWBOIncNative();
    } catch (...) {
        Py_DECREF((PyObject *)s);
        translate_openwbo();
        return nullptr;
    }
    return (PyObject *)s;
}
static void ow_dealloc(PyOpenWBOInc *s) {
    delete s->native;
    s->native = nullptr;
    Py_TYPE(s)->tp_free((PyObject *)s);
}
static PyObject *ow_newvar(PyOpenWBOInc *s, PyObject *) {
    try {
        return PyLong_FromLong(s->native->new_var());
    } catch (...) {
        translate_openwbo();
        return nullptr;
    }
}
static PyObject *ow_add(PyOpenWBOInc *s, PyObject *args, PyObject *kw) {
    static const char *n[] = {"clause", "weight", nullptr};
    PyObject *c, *w = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kw, "O|O:addClause", (char **)n, &c, &w))
        return nullptr;
    PyObject *q = PySequence_Fast(c, "clause must be iterable");
    if (!q)
        return nullptr;
    std::vector<int> cl;
    try {
        auto z = PySequence_Fast_GET_SIZE(q);
        cl.reserve((size_t)z);
        for (Py_ssize_t i = 0; i < z; ++i) {
            long x = PyLong_AsLong(PySequence_Fast_GET_ITEM(q, i));
            if (x == -1 && PyErr_Occurred()) {
                Py_DECREF(q);
                return nullptr;
            }
            if (x == 0 || x <= INT_MIN || x > INT_MAX) {
                Py_DECREF(q);
                PyErr_SetString(x == 0 ? PyExc_ValueError : PyExc_OverflowError, "invalid literal");
                return nullptr;
            }
            cl.push_back((int)x);
        }
        Py_DECREF(q);
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
        s->native->add_clause(cl, soft, weight);
        Py_RETURN_NONE;
    } catch (...) {
        Py_DECREF(q);
        translate_openwbo();
        return nullptr;
    }
}
static PyObject *ow_solve(PyOpenWBOInc *s, PyObject *) {
    try {
        bool r = false;
        std::exception_ptr e;
        Py_BEGIN_ALLOW_THREADS try { r = s->native->solve(); } catch (...) {
            e = std::current_exception();
        }
        Py_END_ALLOW_THREADS if (e) std::rethrow_exception(e);
        return PyBool_FromLong(r);
    } catch (...) {
        translate_openwbo();
        return nullptr;
    }
}
static PyObject *ow_cost(PyOpenWBOInc *s, PyObject *) {
    try {
        return PyLong_FromUnsignedLongLong(s->native->cost());
    } catch (...) {
        translate_openwbo();
        return nullptr;
    }
}
static PyObject *ow_value(PyOpenWBOInc *s, PyObject *arg) {
    long x = PyLong_AsLong(arg);
    if (x == -1 && PyErr_Occurred())
        return nullptr;
    if (x <= INT_MIN || x > INT_MAX) {
        PyErr_SetString(PyExc_OverflowError, "variable out of range");
        return nullptr;
    }
    try {
        return PyBool_FromLong(s->native->value((int)x));
    } catch (...) {
        translate_openwbo();
        return nullptr;
    }
}
static PyMethodDef ow_methods[] = {
    {"newVar", (PyCFunction)ow_newvar, METH_NOARGS, nullptr},
    {"addClause", (PyCFunction)(void (*)(void))ow_add, METH_VARARGS | METH_KEYWORDS, nullptr},
    {"solve", (PyCFunction)ow_solve, METH_NOARGS, nullptr},
    {"getCost", (PyCFunction)ow_cost, METH_NOARGS, nullptr},
    {"getValue", (PyCFunction)ow_value, METH_O, nullptr},
    {nullptr, nullptr, 0, nullptr}};
static PyModuleDef ow_module = {PyModuleDef_HEAD_INIT, "openwbo_inc", "Open-WBO-Inc native binding",
                                -1, nullptr};
PyMODINIT_FUNC PyInit_openwbo_inc() {
    OpenWBOIncType.tp_name = "openwbo_inc.OpenWBOInc";
    OpenWBOIncType.tp_basicsize = sizeof(PyOpenWBOInc);
    OpenWBOIncType.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    OpenWBOIncType.tp_new = ow_new;
    OpenWBOIncType.tp_dealloc = (destructor)ow_dealloc;
    OpenWBOIncType.tp_methods = ow_methods;
    if (PyType_Ready(&OpenWBOIncType) < 0)
        return nullptr;
    PyObject *m = PyModule_Create(&ow_module);
    if (!m)
        return nullptr;
    Py_INCREF(&OpenWBOIncType);
    if (PyModule_AddObject(m, "OpenWBOInc", (PyObject *)&OpenWBOIncType) < 0) {
        Py_DECREF(&OpenWBOIncType);
        Py_DECREF(m);
        return nullptr;
    }
    return m;
}
