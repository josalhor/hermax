#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "openwbo_native.h"
#include <new>
#include <vector>
#include <stdexcept>
#include <limits>
#include <exception>

struct PySolver {
    PyObject_HEAD openwbo_native::Solver *solver;
};
static PyTypeObject OLLType = {PyVarObject_HEAD_INIT(nullptr, 0)};
static PyTypeObject PartType = {PyVarObject_HEAD_INIT(nullptr, 0)};
static PyTypeObject AutoType = {PyVarObject_HEAD_INIT(nullptr, 0)};

static void translate_exception() {
    try {
        throw;
    } catch (const std::invalid_argument &e) {
        PyErr_SetString(PyExc_ValueError, e.what());
    } catch (const std::bad_alloc &) {
        PyErr_NoMemory();
    } catch (const std::exception &e) {
        PyErr_SetString(PyExc_RuntimeError, e.what());
    } catch (...) {
        PyErr_SetString(PyExc_RuntimeError, "Unknown C++ exception");
    }
}
static PyObject *make_solver(PyTypeObject *type, openwbo_native::Solver::Kind kind) {
    PySolver *self = (PySolver *)type->tp_alloc(type, 0);
    if (!self)
        return nullptr;
    self->solver = nullptr;
    try {
        self->solver = new openwbo_native::Solver(kind);
    } catch (...) {
        Py_DECREF((PyObject *)self);
        translate_exception();
        return nullptr;
    }
    return (PyObject *)self;
}
static PyObject *oll_new(PyTypeObject *t, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {nullptr};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "", const_cast<char **>(names)))
        return nullptr;
    return make_solver(t, openwbo_native::Solver::Kind::OLL);
}
static PyObject *part_new(PyTypeObject *t, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {nullptr};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "", const_cast<char **>(names)))
        return nullptr;
    return make_solver(t, openwbo_native::Solver::Kind::PartMSU3);
}
static PyObject *auto_new(PyTypeObject *t, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {nullptr};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "", const_cast<char **>(names)))
        return nullptr;
    return make_solver(t, openwbo_native::Solver::Kind::Auto);
}
static void solver_dealloc(PySolver *self) {
    delete self->solver;
    self->solver = nullptr;
    Py_TYPE(self)->tp_free((PyObject *)self);
}
static int sequence_ints(PyObject *obj, std::vector<int> &out, const char *what) {
    PyObject *seq = PySequence_Fast(obj, what);
    if (!seq)
        return -1;
    Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    try {
        out.reserve((size_t)n);
        for (Py_ssize_t i = 0; i < n; ++i) {
            long v = PyLong_AsLong(PySequence_Fast_GET_ITEM(seq, i));
            if (v == -1 && PyErr_Occurred()) {
                Py_DECREF(seq);
                return -1;
            }
            if (v <= std::numeric_limits<int>::min() || v > std::numeric_limits<int>::max()) {
                Py_DECREF(seq);
                PyErr_SetString(PyExc_OverflowError, "integer does not fit in C int");
                return -1;
            }
            out.push_back((int)v);
        }
    } catch (...) {
        Py_DECREF(seq);
        translate_exception();
        return -1;
    }
    Py_DECREF(seq);
    return 0;
}
static PyObject *solver_new_var(PySolver *s, PyObject *) {
    try {
        return PyLong_FromLong(s->solver->new_var());
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *solver_add_clause(PySolver *s, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {"clause", "weight", nullptr};
    PyObject *clause, *weight = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O:addClause", (char **)names, &clause,
                                     &weight))
        return nullptr;
    std::vector<int> lits;
    if (sequence_ints(clause, lits, "clause must be an iterable of integers") < 0)
        return nullptr;
    bool has = weight != Py_None;
    long long w = 0;
    if (has) {
        w = PyLong_AsLongLong(weight);
        if (w == -1 && PyErr_Occurred())
            return nullptr;
    }
    try {
        s->solver->add_clause(lits, has, w);
        Py_RETURN_NONE;
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *solver_solve(PySolver *s, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {"assumptions", nullptr};
    PyObject *assumptions = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|O:solve", (char **)names, &assumptions))
        return nullptr;
    std::vector<int> a;
    bool has = assumptions != Py_None;
    if (has && sequence_ints(assumptions, a, "assumptions must be an iterable of integers") < 0)
        return nullptr;
    bool result = false;
    std::exception_ptr error;
    Py_BEGIN_ALLOW_THREADS try { result = s->solver->solve(a, has); } catch (...) {
        error = std::current_exception();
    }
    Py_END_ALLOW_THREADS if (error) {
        try {
            std::rethrow_exception(error);
        } catch (...) {
            translate_exception();
            return nullptr;
        }
    }
    return PyBool_FromLong(result);
}
static PyObject *solver_get_cost(PySolver *s, PyObject *) {
    try {
        return PyLong_FromUnsignedLongLong(s->solver->get_cost());
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *solver_get_value(PySolver *s, PyObject *arg) {
    long v = PyLong_AsLong(arg);
    if (v == -1 && PyErr_Occurred())
        return nullptr;
    if (v <= std::numeric_limits<int>::min() || v > std::numeric_limits<int>::max()) {
        PyErr_SetString(PyExc_OverflowError, "variable does not fit in C int");
        return nullptr;
    }
    try {
        return PyBool_FromLong(s->solver->get_value((int)v));
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyMethodDef methods[] = {
    {"newVar", (PyCFunction)solver_new_var, METH_NOARGS, nullptr},
    {"addClause", (PyCFunction)(void (*)(void))solver_add_clause, METH_VARARGS | METH_KEYWORDS,
     nullptr},
    {"solve", (PyCFunction)(void (*)(void))solver_solve, METH_VARARGS | METH_KEYWORDS, nullptr},
    {"getCost", (PyCFunction)solver_get_cost, METH_NOARGS, nullptr},
    {"getValue", (PyCFunction)solver_get_value, METH_O, nullptr},
    {nullptr, nullptr, 0, nullptr}};
static int ready_type(PyTypeObject *t, const char *name, newfunc ctor) {
    t->tp_name = name;
    t->tp_basicsize = sizeof(PySolver);
    t->tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    t->tp_new = ctor;
    t->tp_dealloc = (destructor)solver_dealloc;
    t->tp_methods = methods;
    return PyType_Ready(t);
}
static PyModuleDef module = {PyModuleDef_HEAD_INIT, "openwbo",
                             "Open-WBO (OLL, PartMSU3/MSU3, Auto) — rebuild-on-solve + "
                             "unit-by-literal last-wins + assumptions",
                             -1, nullptr};
static int add_type(PyObject *m, const char *name, PyTypeObject *type) {
    Py_INCREF(type);
    if (PyModule_AddObject(m, name, (PyObject *)type) < 0) {
        Py_DECREF(type);
        return -1;
    }
    return 0;
}
PyMODINIT_FUNC PyInit_openwbo(void) {
    PyObject *m = PyModule_Create(&module);
    if (!m)
        return nullptr;
    if (ready_type(&OLLType, "openwbo.OLL", oll_new) < 0 ||
        ready_type(&PartType, "openwbo.PartMSU3", part_new) < 0 ||
        ready_type(&AutoType, "openwbo.Auto", auto_new) < 0 || add_type(m, "OLL", &OLLType) < 0 ||
        add_type(m, "PartMSU3", &PartType) < 0 || add_type(m, "Auto", &AutoType) < 0) {
        Py_DECREF(m);
        return nullptr;
    }
    return m;
}
