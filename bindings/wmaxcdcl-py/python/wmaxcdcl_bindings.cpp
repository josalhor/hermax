#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "../wmaxcdcl_native.h"
#include <exception>
#include <limits>
#include <new>
#include <stdexcept>
#include <vector>
typedef struct {
    PyObject_HEAD wmaxcdcl_native::Solver *solver;
} PyWMaxCDCL;
static PyTypeObject WMaxCDCLType = {PyVarObject_HEAD_INIT(nullptr, 0)};
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
static PyObject *wm_new(PyTypeObject *t, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {nullptr};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "", const_cast<char **>(names)))
        return nullptr;
    auto *self = reinterpret_cast<PyWMaxCDCL *>(t->tp_alloc(t, 0));
    if (!self)
        return nullptr;
    self->solver = nullptr;
    try {
        self->solver = new wmaxcdcl_native::Solver();
    } catch (...) {
        Py_DECREF(reinterpret_cast<PyObject *>(self));
        translate_exception();
        return nullptr;
    }
    return reinterpret_cast<PyObject *>(self);
}
static void wm_dealloc(PyWMaxCDCL *self) {
    delete self->solver;
    self->solver = nullptr;
    Py_TYPE(self)->tp_free(reinterpret_cast<PyObject *>(self));
}
static int to_ints(PyObject *obj, std::vector<int> &out, const char *msg) {
    PyObject *seq = PySequence_Fast(obj, msg);
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
static PyObject *wm_new_var(PyWMaxCDCL *self, PyObject *args, PyObject *kwargs) {
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
static PyObject *wm_add_clause(PyWMaxCDCL *self, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {"clause", "weight", nullptr};
    PyObject *clause, *weight = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O:addClause", const_cast<char **>(names),
                                     &clause, &weight))
        return nullptr;
    std::vector<int> lits;
    if (to_ints(clause, lits, "clause must be an iterable of integers") < 0)
        return nullptr;
    bool has = weight != Py_None;
    long long w = 0;
    if (has) {
        w = PyLong_AsLongLong(weight);
        if (w == -1 && PyErr_Occurred())
            return nullptr;
    }
    try {
        return PyBool_FromLong(self->solver->add_clause(lits, has, w));
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *wm_set_vars(PyWMaxCDCL *self, PyObject *arg) {
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
static PyObject *wm_prepare(PyWMaxCDCL *self, PyObject *) {
    try {
        self->solver->prepare();
        Py_RETURN_NONE;
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *wm_solve(PyWMaxCDCL *self, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {"assumptions", nullptr};
    PyObject *obj = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|O:solve", const_cast<char **>(names), &obj))
        return nullptr;
    std::vector<int> a;
    if (obj != Py_None && to_ints(obj, a, "assumptions must be an iterable of integers") < 0)
        return nullptr;
    bool result = false;
    std::exception_ptr error;
    Py_BEGIN_ALLOW_THREADS try { result = self->solver->solve(a, obj != Py_None); } catch (...) {
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
static PyObject *wm_cost(PyWMaxCDCL *self, PyObject *) {
    try {
        return PyLong_FromLongLong(self->solver->get_cost());
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyObject *wm_value(PyWMaxCDCL *self, PyObject *arg) {
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
static PyObject *wm_model(PyWMaxCDCL *self, PyObject *) {
    try {
        auto model = self->solver->get_model();
        PyObject *list = PyList_New(model.size());
        if (!list)
            return nullptr;
        for (size_t i = 0; i < model.size(); ++i) {
            PyObject *v = PyLong_FromLong(model[i]);
            if (!v) {
                Py_DECREF(list);
                return nullptr;
            }
            PyList_SET_ITEM(list, i, v);
        }
        return list;
    } catch (...) {
        translate_exception();
        return nullptr;
    }
}
static PyMethodDef methods[] = {
    {"newVar", reinterpret_cast<PyCFunction>(wm_new_var), METH_VARARGS | METH_KEYWORDS, nullptr},
    {"addClause", reinterpret_cast<PyCFunction>(wm_add_clause), METH_VARARGS | METH_KEYWORDS,
     nullptr},
    {"setNInputVars", reinterpret_cast<PyCFunction>(wm_set_vars), METH_O, nullptr},
    {"prepare", reinterpret_cast<PyCFunction>(wm_prepare), METH_NOARGS, nullptr},
    {"solve", reinterpret_cast<PyCFunction>(wm_solve), METH_VARARGS | METH_KEYWORDS, nullptr},
    {"getCost", reinterpret_cast<PyCFunction>(wm_cost), METH_NOARGS, nullptr},
    {"getValue", reinterpret_cast<PyCFunction>(wm_value), METH_O, nullptr},
    {"getModel", reinterpret_cast<PyCFunction>(wm_model), METH_NOARGS, nullptr},
    {nullptr, nullptr, 0, nullptr}};
static PyModuleDef module = {PyModuleDef_HEAD_INIT, "wmaxcdcl", "WMaxCDCL native Python binding",
                             -1, nullptr};
PyMODINIT_FUNC PyInit_wmaxcdcl() {
    WMaxCDCLType.tp_name = "wmaxcdcl.WMaxCDCL";
    WMaxCDCLType.tp_basicsize = sizeof(PyWMaxCDCL);
    WMaxCDCLType.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    WMaxCDCLType.tp_new = wm_new;
    WMaxCDCLType.tp_dealloc = reinterpret_cast<destructor>(wm_dealloc);
    WMaxCDCLType.tp_methods = methods;
    if (PyType_Ready(&WMaxCDCLType) < 0)
        return nullptr;
    PyObject *m = PyModule_Create(&module);
    if (!m)
        return nullptr;
    Py_INCREF(&WMaxCDCLType);
    if (PyModule_AddObject(m, "WMaxCDCL", reinterpret_cast<PyObject *>(&WMaxCDCLType)) < 0) {
        Py_DECREF(&WMaxCDCLType);
        Py_DECREF(m);
        return nullptr;
    }
    return m;
}
