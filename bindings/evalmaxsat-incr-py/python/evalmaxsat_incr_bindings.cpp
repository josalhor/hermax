#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "../evalmaxsat_incr_native.h"
#include <exception>
#include <limits>
#include <new>
#include <stdexcept>
#include <vector>

typedef struct {
    PyObject_HEAD evalmaxsat_incr_native::Solver *solver;
} PyEvalMaxSATIncr;
static PyTypeObject EvalMaxSATIncrType = {PyVarObject_HEAD_INIT(nullptr, 0)};
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

    auto *self = reinterpret_cast<PyEvalMaxSATIncr *>(type->tp_alloc(type, 0));
    if (!self)
        return nullptr;
    self->solver = nullptr;
    try {
        self->solver = new evalmaxsat_incr_native::Solver();
    } catch (...) {
        Py_DECREF(reinterpret_cast<PyObject *>(self));
        translate_exception();
        return nullptr;
    }
    return reinterpret_cast<PyObject *>(self);
}
static void eval_dealloc(PyEvalMaxSATIncr *self) {
    delete self->solver;
    self->solver = nullptr;
    Py_TYPE(self)->tp_free(reinterpret_cast<PyObject *>(self));
}
static int to_int_vector(PyObject *value, std::vector<int> &out, const char *message) {
    PyObject *seq = PySequence_Fast(value, message);
    if (!seq)
        return -1;
    Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
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
static PyObject *eval_add_clause(PyEvalMaxSATIncr *self, PyObject *args, PyObject *kwargs) {
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
        long long v = PyLong_AsLongLong(weight);
        if (v == -1 && PyErr_Occurred())
            return nullptr;
        native_weight = v;
    }
    try {
        self->solver->add_clause(lits, native_weight);
        Py_RETURN_NONE;
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *eval_add_soft(PyEvalMaxSATIncr *self, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {"lit", "weight", nullptr};
    int lit;
    PyObject *weight_obj;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "iO:addSoftLit", const_cast<char **>(names),
                                     &lit, &weight_obj))
        return nullptr;
    unsigned long long weight = PyLong_AsUnsignedLongLong(weight_obj);
    if (weight == static_cast<unsigned long long>(-1) && PyErr_Occurred())
        return nullptr;
    try {
        self->solver->add_soft_lit(lit, static_cast<uint64_t>(weight));
        Py_RETURN_NONE;
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *eval_assume(PyEvalMaxSATIncr *self, PyObject *arg) {
    std::vector<int> assumptions;
    if (to_int_vector(arg, assumptions, "assumptions must be an iterable of integers") < 0)
        return nullptr;
    try {
        self->solver->assume(assumptions);
        Py_RETURN_NONE;
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *eval_solve(PyEvalMaxSATIncr *self, PyObject *) {
    int result = 0;
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
    return PyLong_FromLong(result);
}
static PyObject *eval_cost(PyEvalMaxSATIncr *self, PyObject *) {
    try {
        return PyLong_FromUnsignedLongLong(self->solver->get_cost());
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *eval_value(PyEvalMaxSATIncr *self, PyObject *arg) {
    long lit = PyLong_AsLong(arg);
    if (lit == -1 && PyErr_Occurred())
        return nullptr;
    if (lit <= std::numeric_limits<int>::min() || lit > std::numeric_limits<int>::max()) {
        PyErr_SetString(PyExc_OverflowError, "literal does not fit in C int");
        return nullptr;
    }
    try {
        int v = self->solver->get_value(static_cast<int>(lit));
        if (v == lit)
            Py_RETURN_TRUE;
        if (v == -lit)
            Py_RETURN_FALSE;
        Py_RETURN_NONE;
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *eval_signature(PyEvalMaxSATIncr *self, PyObject *) {
    try {
        std::string sig = self->solver->signature();
        return PyUnicode_FromStringAndSize(sig.data(), static_cast<Py_ssize_t>(sig.size()));
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *eval_assume_keywords(PyEvalMaxSATIncr *self, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {"assumptions", nullptr};
    PyObject *value;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O:assume", const_cast<char **>(names), &value))
        return nullptr;
    return eval_assume(self, value);
}
static PyObject *eval_value_keywords(PyEvalMaxSATIncr *self, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {"lit", nullptr};
    PyObject *value;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O:getValue", const_cast<char **>(names),
                                     &value))
        return nullptr;
    return eval_value(self, value);
}
static PyMethodDef methods[] = {
    {"addClause", reinterpret_cast<PyCFunction>(eval_add_clause), METH_VARARGS | METH_KEYWORDS,
     nullptr},
    {"addSoftLit", reinterpret_cast<PyCFunction>(eval_add_soft), METH_VARARGS | METH_KEYWORDS,
     nullptr},
    {"assume", reinterpret_cast<PyCFunction>(eval_assume_keywords), METH_VARARGS | METH_KEYWORDS,
     nullptr},
    {"solve", reinterpret_cast<PyCFunction>(eval_solve), METH_NOARGS, nullptr},
    {"getCost", reinterpret_cast<PyCFunction>(eval_cost), METH_NOARGS, nullptr},
    {"getValue", reinterpret_cast<PyCFunction>(eval_value_keywords), METH_VARARGS | METH_KEYWORDS,
     nullptr},
    {"signature", reinterpret_cast<PyCFunction>(eval_signature), METH_NOARGS, nullptr},
    {nullptr, nullptr, 0, nullptr}};
static PyModuleDef module = {PyModuleDef_HEAD_INIT, "evalmaxsat_incr", "EvalMaxSATIncr (IPAMIR)",
                             -1, nullptr};
PyMODINIT_FUNC PyInit_evalmaxsat_incr() {
    EvalMaxSATIncrType.tp_name = "evalmaxsat_incr.EvalMaxSATIncr";
    EvalMaxSATIncrType.tp_basicsize = sizeof(PyEvalMaxSATIncr);
    EvalMaxSATIncrType.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    EvalMaxSATIncrType.tp_new = eval_new;
    EvalMaxSATIncrType.tp_dealloc = reinterpret_cast<destructor>(eval_dealloc);
    EvalMaxSATIncrType.tp_methods = methods;
    if (PyType_Ready(&EvalMaxSATIncrType) < 0)
        return nullptr;
    PyObject *m = PyModule_Create(&module);
    if (!m)
        return nullptr;
    Py_INCREF(&EvalMaxSATIncrType);
    if (PyModule_AddObject(m, "EvalMaxSATIncr", reinterpret_cast<PyObject *>(&EvalMaxSATIncrType)) <
        0) {
        Py_DECREF(&EvalMaxSATIncrType);
        Py_DECREF(m);
        return nullptr;
    }
    return m;
}
