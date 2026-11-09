#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "../evalmaxsat_native.h"
#include <exception>
#include <limits>
#include <new>
#include <stdexcept>
#include <vector>

typedef struct {
    PyObject_HEAD evalmaxsat_native::Solver *solver;
} PyEvalMaxSAT;
static PyTypeObject EvalMaxSATType = {PyVarObject_HEAD_INIT(nullptr, 0)};

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

static PyObject *eval_new(PyTypeObject *type, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {nullptr};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "", const_cast<char **>(names)))
        return nullptr;

    auto *self = reinterpret_cast<PyEvalMaxSAT *>(type->tp_alloc(type, 0));
    if (!self)
        return nullptr;
    self->solver = nullptr;
    try {
        self->solver = new evalmaxsat_native::Solver();
    } catch (...) {
        Py_DECREF(reinterpret_cast<PyObject *>(self));
        translate_exception();
        return nullptr;
    }
    return reinterpret_cast<PyObject *>(self);
}
static void eval_dealloc(PyEvalMaxSAT *self) {
    delete self->solver;
    self->solver = nullptr;
    Py_TYPE(self)->tp_free(reinterpret_cast<PyObject *>(self));
}
static int to_int_vector(PyObject *value, std::vector<int> &out, const char *message) {
    PyObject *seq = PySequence_Fast(value, message);
    if (!seq)
        return -1;
    const Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    try {
        out.reserve(static_cast<size_t>(n));
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
static PyObject *eval_new_var(PyEvalMaxSAT *self, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {"decisionVar", nullptr};
    int decision = 1;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|p:newVar", const_cast<char **>(names),
                                     &decision))
        return nullptr;
    try {
        return PyLong_FromLong(self->solver->new_var(decision != 0));
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *eval_add_clause(PyEvalMaxSAT *self, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {"clause", "weight", nullptr};
    PyObject *clause, *weight = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O:addClause", const_cast<char **>(names),
                                     &clause, &weight))
        return nullptr;
    std::vector<int> lits;
    if (to_int_vector(clause, lits, "clause must be an iterable of integers") < 0)
        return nullptr;
    std::optional<long long> native_weight;
    if (weight != Py_None) {
        long long w = PyLong_AsLongLong(weight);
        if (w == -1 && PyErr_Occurred())
            return nullptr;
        native_weight = w;
    }
    try {
        return PyLong_FromLong(self->solver->add_clause(lits, native_weight));
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *eval_solve(PyEvalMaxSAT *self, PyObject *) {
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
static PyObject *eval_cost(PyEvalMaxSAT *self, PyObject *) {
    try {
        return PyLong_FromLongLong(self->solver->get_cost());
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *eval_value(PyEvalMaxSAT *self, PyObject *arg) {
    long lit = PyLong_AsLong(arg);
    if (lit == -1 && PyErr_Occurred())
        return nullptr;
    if (lit <= std::numeric_limits<int>::min() || lit > std::numeric_limits<int>::max()) {
        PyErr_SetString(PyExc_OverflowError, "literal does not fit in C int");
        return nullptr;
    }
    try {
        return PyBool_FromLong(self->solver->get_value(static_cast<int>(lit)));
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *eval_model(PyEvalMaxSAT *self, PyObject *) {
    try {
        auto model = self->solver->get_model();
        PyObject *list = PyList_New(static_cast<Py_ssize_t>(model.size()));
        if (!list)
            return nullptr;
        for (size_t i = 0; i < model.size(); ++i)
            PyList_SET_ITEM(list, static_cast<Py_ssize_t>(i), PyLong_FromLong(model[i]));
        return list;
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *eval_set_n_input_vars(PyEvalMaxSAT *self, PyObject *arg) {
    unsigned long n = PyLong_AsUnsignedLong(arg);
    if (n == static_cast<unsigned long>(-1) && PyErr_Occurred())
        return nullptr;
    if (n > std::numeric_limits<unsigned int>::max()) {
        PyErr_SetString(PyExc_OverflowError, "n does not fit in unsigned int");
        return nullptr;
    }
    try {
        self->solver->set_n_input_vars(static_cast<unsigned int>(n));
        Py_RETURN_NONE;
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyMethodDef eval_methods[] = {
    {"newVar", reinterpret_cast<PyCFunction>(eval_new_var), METH_VARARGS | METH_KEYWORDS, nullptr},
    {"addClause", reinterpret_cast<PyCFunction>(eval_add_clause), METH_VARARGS | METH_KEYWORDS,
     nullptr},
    {"solve", reinterpret_cast<PyCFunction>(eval_solve), METH_NOARGS, nullptr},
    {"getCost", reinterpret_cast<PyCFunction>(eval_cost), METH_NOARGS, nullptr},
    {"getValue", reinterpret_cast<PyCFunction>(eval_value), METH_O, nullptr},
    {"getModel", reinterpret_cast<PyCFunction>(eval_model), METH_NOARGS, nullptr},
    {"setNInputVars", reinterpret_cast<PyCFunction>(eval_set_n_input_vars), METH_O, nullptr},
    {nullptr, nullptr, 0, nullptr}};
static PyModuleDef module = {PyModuleDef_HEAD_INIT, "evalmaxsat_latest", "EvalMaxSAT (Latest)", -1,
                             nullptr};
PyMODINIT_FUNC PyInit_evalmaxsat_latest() {
    EvalMaxSATType.tp_name = "evalmaxsat_latest.EvalMaxSAT";
    EvalMaxSATType.tp_basicsize = sizeof(PyEvalMaxSAT);
    EvalMaxSATType.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    EvalMaxSATType.tp_new = eval_new;
    EvalMaxSATType.tp_dealloc = reinterpret_cast<destructor>(eval_dealloc);
    EvalMaxSATType.tp_methods = eval_methods;
    if (PyType_Ready(&EvalMaxSATType) < 0)
        return nullptr;
    PyObject *m = PyModule_Create(&module);
    if (!m)
        return nullptr;
    Py_INCREF(&EvalMaxSATType);
    if (PyModule_AddObject(m, "EvalMaxSAT", reinterpret_cast<PyObject *>(&EvalMaxSATType)) < 0) {
        Py_DECREF(&EvalMaxSATType);
        Py_DECREF(m);
        return nullptr;
    }
    return m;
}
