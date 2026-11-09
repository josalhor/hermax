#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <cstdint>
#include <vector>
#include <limits>
#include <exception>
#include <stdexcept>
#include "../aperture_native.h"

namespace {
typedef struct {
    PyObject_HEAD ApertureBackend *backend;
} PyAperture;
static PyTypeObject ApertureType = {PyVarObject_HEAD_INIT(nullptr, 0)};
static void translate_exception() {
    try {
        throw;
    } catch (const std::bad_alloc &) {
        PyErr_NoMemory();
    } catch (const std::overflow_error &e) {
        PyErr_SetString(PyExc_OverflowError, e.what());
    } catch (const std::invalid_argument &e) {
        PyErr_SetString(PyExc_ValueError, e.what());
    } catch (const std::exception &e) {
        PyErr_SetString(PyExc_RuntimeError, e.what());
    } catch (...) {
        if (!PyErr_Occurred())
            PyErr_SetString(PyExc_RuntimeError, "Unknown C++ exception");
    }
}
static int32_t as_literal(PyObject *o) {
    long x = PyLong_AsLong(o);
    if (x == -1 && PyErr_Occurred())
        return 0;
    if (x == 0) {
        PyErr_SetString(PyExc_ValueError, "literal must be nonzero");
        return 0;
    }
    if (x <= INT32_MIN || x > INT32_MAX) {
        PyErr_SetString(PyExc_OverflowError, "literal exceeds Aperture's int32 range");
        return 0;
    }
    return (int32_t)x;
}
static PyObject *ap_new(PyTypeObject *type, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {nullptr};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "", const_cast<char **>(names)))
        return nullptr;

    auto *self = reinterpret_cast<PyAperture *>(type->tp_alloc(type, 0));
    if (!self)
        return nullptr;
    self->backend = nullptr;
    try {
        self->backend = new ApertureBackend();
    } catch (...) {
        Py_DECREF(reinterpret_cast<PyObject *>(self));
        translate_exception();
        return nullptr;
    }
    return reinterpret_cast<PyObject *>(self);
}
static void ap_dealloc(PyAperture *self) {
    delete self->backend;
    self->backend = nullptr;
    Py_TYPE(self)->tp_free(reinterpret_cast<PyObject *>(self));
}
static PyObject *ap_newvar(PyAperture *self, PyObject *) {
    try {
        return PyLong_FromLong(self->backend->new_var());
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *ap_add_clause(PyAperture *self, PyObject *arg) {
    PyObject *seq = PySequence_Fast(arg, "clause must be an iterable of integers");
    if (!seq)
        return nullptr;
    std::vector<int32_t> clause;
    try {
        Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
        clause.reserve((size_t)n);
        for (Py_ssize_t i = 0; i < n; ++i) {
            int32_t lit = as_literal(PySequence_Fast_GET_ITEM(seq, i));
            if (PyErr_Occurred()) {
                Py_DECREF(seq);
                return nullptr;
            }
            clause.push_back(lit);
        }
        Py_DECREF(seq);
        seq = nullptr;
        self->backend->add_clause(clause);
        Py_RETURN_NONE;
    } catch (...) {
        Py_XDECREF(seq);
        translate_exception();
        return nullptr;
    }
}
static PyObject *ap_set_soft(PyAperture *self, PyObject *args) {
    PyObject *lit_obj, *weight_obj;
    if (!PyArg_ParseTuple(args, "OO:set_soft", &lit_obj, &weight_obj))
        return nullptr;
    int32_t lit = as_literal(lit_obj);
    if (PyErr_Occurred())
        return nullptr;
    unsigned long long weight = PyLong_AsUnsignedLongLong(weight_obj);
    if (weight == static_cast<unsigned long long>(-1) && PyErr_Occurred())
        return nullptr;
    try {
        self->backend->set_soft(lit, (uint64_t)weight);
        Py_RETURN_NONE;
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *ap_assume(PyAperture *self, PyObject *arg) {
    int32_t lit = as_literal(arg);
    if (PyErr_Occurred())
        return nullptr;
    try {
        self->backend->assume(lit);
        Py_RETURN_NONE;
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *ap_solve(PyAperture *self, PyObject *) {
    try {
        int r = 0;
        std::exception_ptr e;
        Py_BEGIN_ALLOW_THREADS try { r = self->backend->solve(); } catch (...) {
            e = std::current_exception();
        }
        Py_END_ALLOW_THREADS if (e) std::rethrow_exception(e);
        return PyLong_FromLong(r);
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *ap_cost(PyAperture *self, PyObject *) {
    try {
        return PyLong_FromUnsignedLongLong(self->backend->objective_value());
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *ap_value(PyAperture *self, PyObject *arg) {
    int32_t lit = as_literal(arg);
    if (PyErr_Occurred())
        return nullptr;
    try {
        return PyLong_FromLong(self->backend->value(lit));
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *ap_signature(PyAperture *self, PyObject *) {
    try {
        return PyUnicode_FromString(self->backend->signature());
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyMethodDef ap_methods[] = {{"new_var", (PyCFunction)ap_newvar, METH_NOARGS, nullptr},
                                   {"add_clause", (PyCFunction)ap_add_clause, METH_O, nullptr},
                                   {"set_soft", (PyCFunction)ap_set_soft, METH_VARARGS, nullptr},
                                   {"assume", (PyCFunction)ap_assume, METH_O, nullptr},
                                   {"solve", (PyCFunction)ap_solve, METH_NOARGS, nullptr},
                                   {"objective_value", (PyCFunction)ap_cost, METH_NOARGS, nullptr},
                                   {"value", (PyCFunction)ap_value, METH_O, nullptr},
                                   {"signature", (PyCFunction)ap_signature, METH_NOARGS, nullptr},
                                   {nullptr, nullptr, 0, nullptr}};
static PyModuleDef ap_module = {PyModuleDef_HEAD_INIT, "_aperture_native",
                                "Hermax native bridge for Aperture's IPAMIR implementation", -1,
                                nullptr};
} // namespace
PyMODINIT_FUNC PyInit__aperture_native(void) {
    ApertureType.tp_name = "_aperture_native.Aperture";
    ApertureType.tp_basicsize = sizeof(PyAperture);
    ApertureType.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    ApertureType.tp_new = ap_new;
    ApertureType.tp_dealloc = (destructor)ap_dealloc;
    ApertureType.tp_methods = ap_methods;
    if (PyType_Ready(&ApertureType) < 0)
        return nullptr;
    PyObject *m = PyModule_Create(&ap_module);
    if (!m)
        return nullptr;
    Py_INCREF(&ApertureType);
    if (PyModule_AddObject(m, "Aperture", (PyObject *)&ApertureType) < 0) {
        Py_DECREF(&ApertureType);
        Py_DECREF(m);
        return nullptr;
    }
    return m;
}
