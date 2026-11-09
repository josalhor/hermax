#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "../loandra_native.h"
#include <exception>
#include <limits>
#include <new>
#include <stdexcept>
#include <vector>
typedef struct {
    PyObject_HEAD loandra_native::Solver *solver;
} PyLoandra;
static PyTypeObject LoandraType = {PyVarObject_HEAD_INIT(nullptr, 0)};
static void translate_exception() {
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
static PyObject *loandra_new(PyTypeObject *t, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {nullptr};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "", const_cast<char **>(names)))
        return nullptr;
    auto *self = reinterpret_cast<PyLoandra *>(t->tp_alloc(t, 0));
    if (!self)
        return nullptr;
    self->solver = nullptr;
    try {
        self->solver = new loandra_native::Solver();
    } catch (...) {
        Py_DECREF(reinterpret_cast<PyObject *>(self));
        translate_exception();
        return nullptr;
    }
    return reinterpret_cast<PyObject *>(self);
}
static void loandra_dealloc(PyLoandra *self) {
    delete self->solver;
    self->solver = nullptr;
    Py_TYPE(self)->tp_free(reinterpret_cast<PyObject *>(self));
}
static int int_vector(PyObject *obj, std::vector<int> &out) {
    PyObject *seq = PySequence_Fast(obj, "clause must be an iterable of integers");
    if (!seq)
        return -1;
    Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    try {
        out.reserve(n);
        for (Py_ssize_t i = 0; i < n; ++i) {
            long v = PyLong_AsLong(PySequence_Fast_GET_ITEM(seq, i));
            if (v == -1 && PyErr_Occurred()) {
                Py_DECREF(seq);
                return -1;
            }
            if (v <= std::numeric_limits<int>::min() || v > std::numeric_limits<int>::max()) {
                Py_DECREF(seq);
                PyErr_SetString(PyExc_OverflowError, "literal does not fit in C int");
                return -1;
            }
            out.push_back(static_cast<int>(v));
        }
    } catch (...) {
        Py_DECREF(seq);
        translate_exception();
        return -1;
    }
    Py_DECREF(seq);
    return 0;
}
static PyObject *loandra_new_var(PyLoandra *self, PyObject *) {
    try {
        return PyLong_FromLong(self->solver->new_var());
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *loandra_add_clause(PyLoandra *self, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {"clause", "weight", nullptr};
    PyObject *clause, *weight = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O:addClause", const_cast<char **>(names),
                                     &clause, &weight))
        return nullptr;
    std::vector<int> lits;
    if (int_vector(clause, lits) < 0)
        return nullptr;
    bool has = weight != Py_None;
    long long w = 0;
    if (has) {
        w = PyLong_AsLongLong(weight);
        if (w == -1 && PyErr_Occurred())
            return nullptr;
    }
    try {
        self->solver->add_clause(lits, has, w);
        Py_RETURN_NONE;
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *loandra_solve(PyLoandra *self, PyObject *) {
    bool result = false;
    std::exception_ptr error;
    Py_BEGIN_ALLOW_THREADS try { result = self->solver->solve(); } catch (...) {
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
static PyObject *loandra_cost(PyLoandra *self, PyObject *) {
    try {
        return PyLong_FromUnsignedLongLong(self->solver->get_cost());
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *loandra_value(PyLoandra *self, PyObject *arg) {
    long v = PyLong_AsLong(arg);
    if (v == -1 && PyErr_Occurred())
        return nullptr;
    if (v <= std::numeric_limits<int>::min() || v > std::numeric_limits<int>::max()) {
        PyErr_SetString(PyExc_OverflowError, "variable id does not fit in C int");
        return nullptr;
    }
    try {
        return PyBool_FromLong(self->solver->get_value(static_cast<int>(v)));
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *loandra_model(PyLoandra *self, PyObject *) {
    try {
        auto model = self->solver->get_model();
        PyObject *list = PyList_New(model.size());
        if (!list)
            return nullptr;
        for (size_t i = 0; i < model.size(); ++i) {
            PyObject *value = PyLong_FromLong(model[i]);
            if (!value) {
                Py_DECREF(list);
                return nullptr;
            }
            PyList_SET_ITEM(list, i, value);
        }
        return list;
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyMethodDef methods[] = {
    {"newVar", reinterpret_cast<PyCFunction>(loandra_new_var), METH_NOARGS, nullptr},
    {"addClause", reinterpret_cast<PyCFunction>(loandra_add_clause), METH_VARARGS | METH_KEYWORDS,
     nullptr},
    {"solve", reinterpret_cast<PyCFunction>(loandra_solve), METH_NOARGS, nullptr},
    {"getCost", reinterpret_cast<PyCFunction>(loandra_cost), METH_NOARGS, nullptr},
    {"getValue", reinterpret_cast<PyCFunction>(loandra_value), METH_O, nullptr},
    {"getModel", reinterpret_cast<PyCFunction>(loandra_model), METH_NOARGS, nullptr},
    {nullptr, nullptr, 0, nullptr}};
static PyModuleDef module = {PyModuleDef_HEAD_INIT, "loandra", "Loandra (OLL path)", -1, nullptr};
PyMODINIT_FUNC PyInit_loandra() {
    LoandraType.tp_name = "loandra.Loandra";
    LoandraType.tp_basicsize = sizeof(PyLoandra);
    LoandraType.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    LoandraType.tp_new = loandra_new;
    LoandraType.tp_dealloc = reinterpret_cast<destructor>(loandra_dealloc);
    LoandraType.tp_methods = methods;
    if (PyType_Ready(&LoandraType) < 0)
        return nullptr;
    PyObject *m = PyModule_Create(&module);
    if (!m)
        return nullptr;
    Py_INCREF(&LoandraType);
    if (PyModule_AddObject(m, "Loandra", reinterpret_cast<PyObject *>(&LoandraType)) < 0) {
        Py_DECREF(&LoandraType);
        Py_DECREF(m);
        return nullptr;
    }
    return m;
}
