#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <exception>
#include <optional>
#include <cmath>
#include <csignal>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

#include "coretrail/coretrail_solver.hpp"

typedef struct {
    PyObject_HEAD
    coretrail::CoreTrailSolver* solver;
} PyCoreTrail;

namespace {

volatile std::sig_atomic_t sigint_requested = 0;
std::mutex sigint_relay_mutex;

void coretrail_sigint_handler(int) {
    sigint_requested = 1;
}

bool coretrail_sigint_pending() noexcept {
    return sigint_requested != 0;
}

class SigintRelay {
public:
    explicit SigintRelay(coretrail::CoreTrailSolver* solver)
        : solver_(solver), lock_(sigint_relay_mutex) {
        sigint_requested = 0;
        previous_handler_ = PyOS_setsig(SIGINT, coretrail_sigint_handler);
        solver_->set_interrupt_probe(coretrail_sigint_pending);
    }

    ~SigintRelay() {
        solver_->set_interrupt_probe(nullptr);
        PyOS_setsig(SIGINT, previous_handler_);
        sigint_requested = 0;
    }

private:
    coretrail::CoreTrailSolver* solver_;
    std::unique_lock<std::mutex> lock_;
    PyOS_sighandler_t previous_handler_{nullptr};
};

}  // namespace

static int py_to_int_vector(PyObject* seq, std::vector<int>* out) {
    PyObject* it = PyObject_GetIter(seq);
    if (it == nullptr) return -1;
    PyObject* x = nullptr;
    while ((x = PyIter_Next(it)) != nullptr) {
        long v = PyLong_AsLong(x);
        Py_DECREF(x);
        if (PyErr_Occurred()) {
            Py_DECREF(it);
            return -1;
        }
        out->push_back(static_cast<int>(v));
    }
    Py_DECREF(it);
    if (PyErr_Occurred()) return -1;
    return 0;
}

static int load_formula_from_wcnf(coretrail::CoreTrailSolver* solver, PyObject* formula) {
    PyObject* nv_obj = PyObject_GetAttrString(formula, "nv");
    if (nv_obj == nullptr) return -1;
    long nv = PyLong_AsLong(nv_obj);
    Py_DECREF(nv_obj);
    if (PyErr_Occurred()) return -1;
    solver->initialize_external_vars(static_cast<int>(nv));

    PyObject* hard = PyObject_GetAttrString(formula, "hard");
    PyObject* soft = PyObject_GetAttrString(formula, "soft");
    PyObject* wght = PyObject_GetAttrString(formula, "wght");
    PyObject* atms = PyObject_GetAttrString(formula, "atms");
    if (hard == nullptr || soft == nullptr || wght == nullptr) {
        Py_XDECREF(hard); Py_XDECREF(soft); Py_XDECREF(wght); Py_XDECREF(atms);
        return -1;
    }
    if (atms != nullptr) {
        Py_ssize_t asz = PySequence_Size(atms);
        if (asz < 0) {
            Py_DECREF(hard); Py_DECREF(soft); Py_DECREF(wght); Py_DECREF(atms);
            return -1;
        }
        if (asz > 0) {
            Py_DECREF(hard); Py_DECREF(soft); Py_DECREF(wght); Py_DECREF(atms);
            PyErr_SetString(PyExc_NotImplementedError, "CoreTrail does not support native cardinality constraints.");
            return -1;
        }
        Py_DECREF(atms);
    } else {
        PyErr_Clear();
    }

    Py_ssize_t hsz = PySequence_Size(hard);
    if (hsz < 0) {
        Py_DECREF(hard); Py_DECREF(soft); Py_DECREF(wght);
        return -1;
    }
    for (Py_ssize_t i = 0; i < hsz; ++i) {
        PyObject* cl = PySequence_GetItem(hard, i);
        if (cl == nullptr) {
            Py_DECREF(hard); Py_DECREF(soft); Py_DECREF(wght);
            return -1;
        }
        std::vector<int> c;
        if (py_to_int_vector(cl, &c) < 0) {
            Py_DECREF(cl); Py_DECREF(hard); Py_DECREF(soft); Py_DECREF(wght);
            return -1;
        }
        Py_DECREF(cl);
        try {
            solver->add_hard_clause(c);
        } catch (const std::exception& e) {
            Py_DECREF(hard); Py_DECREF(soft); Py_DECREF(wght);
            PyErr_SetString(PyExc_ValueError, e.what());
            return -1;
        }
    }

    Py_ssize_t ssz = PySequence_Size(soft);
    if (ssz < 0) {
        Py_DECREF(hard); Py_DECREF(soft); Py_DECREF(wght);
        return -1;
    }
    for (Py_ssize_t i = 0; i < ssz; ++i) {
        PyObject* cl = PySequence_GetItem(soft, i);
        PyObject* ww = PySequence_GetItem(wght, i);
        if (cl == nullptr || ww == nullptr) {
            Py_XDECREF(cl); Py_XDECREF(ww);
            Py_DECREF(hard); Py_DECREF(soft); Py_DECREF(wght);
            return -1;
        }
        long w = PyLong_AsLong(ww);
        Py_DECREF(ww);
        if (PyErr_Occurred()) {
            Py_DECREF(cl); Py_DECREF(hard); Py_DECREF(soft); Py_DECREF(wght);
            return -1;
        }
        std::vector<int> c;
        if (py_to_int_vector(cl, &c) < 0) {
            Py_DECREF(cl); Py_DECREF(hard); Py_DECREF(soft); Py_DECREF(wght);
            return -1;
        }
        Py_DECREF(cl);
        try {
            solver->add_clause(c, w);
        } catch (const std::exception& e) {
            Py_DECREF(hard); Py_DECREF(soft); Py_DECREF(wght);
            PyErr_SetString(PyExc_ValueError, e.what());
            return -1;
        }
    }

    Py_DECREF(hard);
    Py_DECREF(soft);
    Py_DECREF(wght);
    return 0;
}

static int PyCoreTrail_init(PyCoreTrail* self, PyObject* args, PyObject* kwargs) {
    PyObject* formula = nullptr;
    if (!PyArg_ParseTuple(args, "O", &formula)) return -1;
    coretrail::CoreTrailOptions opts;
    opts.minz = true;
    opts.trim = 0;
    opts.exhaust = false;
    opts.core_memory = false;
    opts.core_replay = 10;
    opts.solver = "g4";
    opts.adapt = true;
    opts.full_stratified = true;
    opts.nohard = true;

    if (kwargs != nullptr) {
        PyObject* v = nullptr;

        v = PyDict_GetItemString(kwargs, "minz");
        if (v) {
            int b = PyObject_IsTrue(v);
            if (b < 0) return -1;
            opts.minz = (b != 0);
        }
        v = PyDict_GetItemString(kwargs, "trim");
        if (v) {
            long t = PyLong_AsLong(v);
            if (PyErr_Occurred()) return -1;
            opts.trim = static_cast<int>(t);
        }
        v = PyDict_GetItemString(kwargs, "exhaust");
        if (v) {
            int b = PyObject_IsTrue(v);
            if (b < 0) return -1;
            opts.exhaust = (b != 0);
        }
        v = PyDict_GetItemString(kwargs, "core_memory");
        if (v) {
            int b = PyObject_IsTrue(v);
            if (b < 0) return -1;
            opts.core_memory = (b != 0);
        }
        v = PyDict_GetItemString(kwargs, "core_replay");
        if (v) {
            long cr = PyLong_AsLong(v);
            if (PyErr_Occurred()) return -1;
            opts.core_replay = static_cast<int>(cr);
        }
        v = PyDict_GetItemString(kwargs, "solver");
        if (v) {
            const char* s = PyUnicode_AsUTF8(v);
            if (s == nullptr) return -1;
            opts.solver = s;
        }
        v = PyDict_GetItemString(kwargs, "adapt");
        if (v) {
            int b = PyObject_IsTrue(v);
            if (b < 0) return -1;
            opts.adapt = (b != 0);
        }
        v = PyDict_GetItemString(kwargs, "full_stratified");
        if (v) {
            int b = PyObject_IsTrue(v);
            if (b < 0) return -1;
            opts.full_stratified = (b != 0);
        }
        v = PyDict_GetItemString(kwargs, "exploit_overlap");
        if (v) {
            int b = PyObject_IsTrue(v);
            if (b < 0) return -1;
            opts.exploit_overlap = (b != 0);
        }
        v = PyDict_GetItemString(kwargs, "blo");
        if (v) {
            const char* s = PyUnicode_AsUTF8(v);
            if (s == nullptr) return -1;
            opts.blo = s;
            if (!(opts.blo == "none" || opts.blo == "basic" || opts.blo == "div" ||
                  opts.blo == "cluster" || opts.blo == "full")) {
                PyErr_SetString(PyExc_AssertionError, "Unknown BLO strategy");
                return -1;
            }
        }
        v = PyDict_GetItemString(kwargs, "incr");
        if (v) {
            int b = PyObject_IsTrue(v);
            if (b < 0) return -1;
            opts.incr = (b != 0);
        }
        v = PyDict_GetItemString(kwargs, "nohard");
        if (v) {
            int b = PyObject_IsTrue(v);
            if (b < 0) return -1;
            opts.nohard = (b != 0);
            if (!opts.nohard) {
                PyErr_SetString(PyExc_AssertionError, "Clause hardening not supported in Incremental MaxSAT");
                return -1;
            }
        }
        (void)PyDict_GetItemString(kwargs, "process");
        v = PyDict_GetItemString(kwargs, "verbose");
        if (v) {
            long vv = PyLong_AsLong(v);
            if (PyErr_Occurred()) return -1;
            opts.verbose = static_cast<int>(vv);
        }
    }
    try {
        self->solver = new coretrail::CoreTrailSolver(opts);
        if (self->solver == nullptr) {
            PyErr_NoMemory();
            return -1;
        }
        if (load_formula_from_wcnf(self->solver, formula) < 0) {
            delete self->solver;
            self->solver = nullptr;
            return -1;
        }
        return 0;
    } catch (const std::invalid_argument& e) {
        PyErr_SetString(PyExc_ValueError, e.what());
        return -1;
    } catch (const std::exception& e) {
        PyErr_SetString(PyExc_RuntimeError, e.what());
        return -1;
    }
}

static void PyCoreTrail_dealloc(PyCoreTrail* self) {
    delete self->solver;
    self->solver = nullptr;
    Py_TYPE(self)->tp_free((PyObject*)self);
}

static inline coretrail::CoreTrailSolver* get_solver(PyCoreTrail* self) {
    if (self->solver == nullptr) {
        PyErr_SetString(PyExc_RuntimeError, "solver not initialized");
        return nullptr;
    }
    return self->solver;
}

static PyObject* m_add_clause(PyCoreTrail* self, PyObject* args, PyObject* kwargs) {
    coretrail::CoreTrailSolver* s = get_solver(self);
    if (s == nullptr) return nullptr;
    PyObject* clause_obj = nullptr;
    PyObject* weight_obj = Py_None;
    if (!PyArg_ParseTuple(args, "O|O", &clause_obj, &weight_obj)) return nullptr;
    if (kwargs != nullptr) {
        PyObject* w = PyDict_GetItemString(kwargs, "weight");
        if (w != nullptr) weight_obj = w;
    }
    std::vector<int> clause;
    if (PyTuple_Check(clause_obj) && PyTuple_Size(clause_obj) >= 2) {
        PyObject* lits_obj = PyTuple_GetItem(clause_obj, 0);  // borrowed
        if (lits_obj == nullptr) return nullptr;
        if (py_to_int_vector(lits_obj, &clause) < 0) return nullptr;
        PyErr_SetString(PyExc_NotImplementedError, "Native cardinality constraints are unsupported in CoreTrail.");
        return nullptr;
    }
    if (py_to_int_vector(clause_obj, &clause) < 0) return nullptr;
    std::optional<long> w = std::nullopt;
    if (weight_obj != Py_None) {
        long wi = PyLong_AsLong(weight_obj);
        if (PyErr_Occurred()) return nullptr;
        w = wi;
    }
    try {
        s->add_clause(clause, w);
    } catch (const std::invalid_argument& e) {
        PyErr_SetString(PyExc_ValueError, e.what());
        return nullptr;
    } catch (const std::exception& e) {
        PyErr_SetString(PyExc_RuntimeError, e.what());
        return nullptr;
    }
    Py_RETURN_NONE;
}

static PyObject* m_set_soft(PyCoreTrail* self, PyObject* args, PyObject* kwargs) {
    coretrail::CoreTrailSolver* s = get_solver(self);
    if (s == nullptr) return nullptr;
    long lit = 0, weight = 0;
    if (!PyArg_ParseTuple(args, "ll", &lit, &weight)) return nullptr;
    if (kwargs != nullptr) {
        PyObject* l = PyDict_GetItemString(kwargs, "lit");
        PyObject* w = PyDict_GetItemString(kwargs, "weight");
        if (l) lit = PyLong_AsLong(l);
        if (w) weight = PyLong_AsLong(w);
        if (PyErr_Occurred()) return nullptr;
    }
    try {
        s->set_soft(static_cast<int>(lit), weight);
    } catch (const std::invalid_argument& e) {
        PyErr_SetString(PyExc_ValueError, e.what());
        return nullptr;
    } catch (const std::exception& e) {
        PyErr_SetString(PyExc_RuntimeError, e.what());
        return nullptr;
    }
    Py_RETURN_NONE;
}

static PyObject* m_add_soft_unit(PyCoreTrail* self, PyObject* args, PyObject* kwargs) {
    coretrail::CoreTrailSolver* s = get_solver(self);
    if (s == nullptr) return nullptr;
    long lit = 0, weight = 0;
    if (!PyArg_ParseTuple(args, "ll", &lit, &weight)) return nullptr;
    if (kwargs != nullptr) {
        PyObject* l = PyDict_GetItemString(kwargs, "lit");
        PyObject* w = PyDict_GetItemString(kwargs, "weight");
        if (l) lit = PyLong_AsLong(l);
        if (w) weight = PyLong_AsLong(w);
        if (PyErr_Occurred()) return nullptr;
    }
    try {
        s->add_soft_unit(static_cast<int>(lit), weight);
    } catch (const std::invalid_argument& e) {
        PyErr_SetString(PyExc_ValueError, e.what());
        return nullptr;
    } catch (const std::exception& e) {
        PyErr_SetString(PyExc_RuntimeError, e.what());
        return nullptr;
    }
    Py_RETURN_NONE;
}

static PyObject* m_solve(PyCoreTrail* self, PyObject* args, PyObject* kwargs) {
    coretrail::CoreTrailSolver* s = get_solver(self);
    if (s == nullptr) return nullptr;
    PyObject* assumptions_obj = Py_None;
    int raise_on_abnormal = 0;
    PyObject* time_limit_obj = Py_None;
    if (!PyArg_ParseTuple(args, "|OpO", &assumptions_obj, &raise_on_abnormal, &time_limit_obj)) return nullptr;
    if (kwargs != nullptr) {
        PyObject* a = PyDict_GetItemString(kwargs, "assumptions");
        PyObject* r = PyDict_GetItemString(kwargs, "raise_on_abnormal");
        PyObject* t = PyDict_GetItemString(kwargs, "time_limit");
        if (a) assumptions_obj = a;
        if (r) raise_on_abnormal = PyObject_IsTrue(r);
        if (t) time_limit_obj = t;
    }
    std::vector<int> assumptions;
    if (assumptions_obj != Py_None && py_to_int_vector(assumptions_obj, &assumptions) < 0) return nullptr;
    std::optional<double> time_limit;
    if (time_limit_obj != Py_None) {
        double value = PyFloat_AsDouble(time_limit_obj);
        if (PyErr_Occurred()) return nullptr;
        if (!std::isfinite(value) || value <= 0.0) {
            PyErr_SetString(PyExc_ValueError, "time_limit must be a finite positive number of seconds");
            return nullptr;
        }
        time_limit = value;
    }
    try {
        bool sat = false;
        std::exception_ptr solve_eptr;
        Py_BEGIN_ALLOW_THREADS
        try {
            SigintRelay sigint_relay(s);
            sat = s->solve(assumptions, raise_on_abnormal != 0, time_limit);
        } catch (...) {
            solve_eptr = std::current_exception();
        }
        Py_END_ALLOW_THREADS
        if (solve_eptr) {
            std::rethrow_exception(solve_eptr);
        }
        if (sat) Py_RETURN_TRUE;
        Py_RETURN_FALSE;
    } catch (const std::runtime_error& e) {
        PyErr_SetString(PyExc_RuntimeError, e.what());
        return nullptr;
    } catch (const std::exception& e) {
        PyErr_SetString(PyExc_RuntimeError, e.what());
        return nullptr;
    }
}

static PyObject* m_get_status(PyCoreTrail* self, PyObject* args) {
    (void)args;
    coretrail::CoreTrailSolver* s = get_solver(self);
    if (s == nullptr) return nullptr;
    return PyLong_FromLong(static_cast<long>(s->get_status()));
}

static PyObject* m_request_stop(PyCoreTrail* self, PyObject* args) {
    (void)args;
    coretrail::CoreTrailSolver* s = get_solver(self);
    if (s == nullptr) return nullptr;
    s->request_stop();
    Py_RETURN_NONE;
}

static PyObject* m_clear_stop(PyCoreTrail* self, PyObject* args) {
    (void)args;
    coretrail::CoreTrailSolver* s = get_solver(self);
    if (s == nullptr) return nullptr;
    s->clear_stop_request();
    Py_RETURN_NONE;
}

static PyObject* m_get_cost(PyCoreTrail* self, PyObject* args) {
    (void)args;
    coretrail::CoreTrailSolver* s = get_solver(self);
    if (s == nullptr) return nullptr;
    try {
        return PyLong_FromLong(s->get_cost());
    } catch (const std::runtime_error& e) {
        PyErr_SetString(PyExc_RuntimeError, e.what());
        return nullptr;
    }
}

static PyObject* m_val(PyCoreTrail* self, PyObject* args) {
    coretrail::CoreTrailSolver* s = get_solver(self);
    if (s == nullptr) return nullptr;
    long lit = 0;
    if (!PyArg_ParseTuple(args, "l", &lit)) return nullptr;
    try {
        return PyLong_FromLong(s->val(static_cast<int>(lit)));
    } catch (const std::runtime_error& e) {
        PyErr_SetString(PyExc_RuntimeError, e.what());
        return nullptr;
    }
}

static PyObject* m_get_model(PyCoreTrail* self, PyObject* args) {
    (void)args;
    coretrail::CoreTrailSolver* s = get_solver(self);
    if (s == nullptr) return nullptr;
    try {
        std::vector<int> m = s->get_model();
        PyObject* out = PyList_New(0);
        if (out == nullptr) return nullptr;
        for (int l : m) {
            PyObject* o = PyLong_FromLong(l);
            if (o == nullptr || PyList_Append(out, o) < 0) {
                Py_XDECREF(o);
                Py_DECREF(out);
                return nullptr;
            }
            Py_DECREF(o);
        }
        return out;
    } catch (const std::runtime_error& e) {
        PyErr_SetString(PyExc_RuntimeError, e.what());
        return nullptr;
    }
}

static PyObject* m_signature(PyCoreTrail* self, PyObject* args) {
    (void)args;
    coretrail::CoreTrailSolver* s = get_solver(self);
    if (s == nullptr) return nullptr;
    return PyUnicode_FromString(s->signature().c_str());
}

static PyObject* m_close(PyCoreTrail* self, PyObject* args) {
    (void)args;
    coretrail::CoreTrailSolver* s = get_solver(self);
    if (s == nullptr) return nullptr;
    s->close();
    Py_RETURN_NONE;
}

static PyMethodDef CoreTrail_methods[] = {
    {"add_clause", (PyCFunction)(void(*)(void))m_add_clause, METH_VARARGS | METH_KEYWORDS, "Add hard/soft clause."},
    {"set_soft", (PyCFunction)(void(*)(void))m_set_soft, METH_VARARGS | METH_KEYWORDS, "Set soft literal."},
    {"add_soft_unit", (PyCFunction)(void(*)(void))m_add_soft_unit, METH_VARARGS | METH_KEYWORDS, "Add soft unit."},
    {"solve", (PyCFunction)(void(*)(void))m_solve, METH_VARARGS | METH_KEYWORDS, "Solve incremental query."},
    {"request_stop", (PyCFunction)m_request_stop, METH_VARARGS, "Request solver stop/interruption."},
    {"clear_stop", (PyCFunction)m_clear_stop, METH_VARARGS, "Clear solver stop/interruption request."},
    {"get_status", (PyCFunction)m_get_status, METH_VARARGS, "Get status."},
    {"get_cost", (PyCFunction)m_get_cost, METH_VARARGS, "Get objective value."},
    {"val", (PyCFunction)m_val, METH_VARARGS, "Get literal value."},
    {"get_model", (PyCFunction)m_get_model, METH_VARARGS, "Get model."},
    {"signature", (PyCFunction)m_signature, METH_VARARGS, "Get signature."},
    {"close", (PyCFunction)m_close, METH_VARARGS, "Close solver."},
    {NULL, NULL, 0, NULL}
};

static PyTypeObject CoreTrailType = {
    PyVarObject_HEAD_INIT(NULL, 0)
};

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    "coretrail_native",
    "CoreTrail native incremental MaxSAT module.",
    -1,
    NULL
};

PyMODINIT_FUNC PyInit_coretrail_native(void) {
    CoreTrailType.tp_name = "coretrail_native.CoreTrail";
    CoreTrailType.tp_basicsize = sizeof(PyCoreTrail);
    CoreTrailType.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    CoreTrailType.tp_doc = "CoreTrail native incremental MaxSAT solver";
    CoreTrailType.tp_methods = CoreTrail_methods;
    CoreTrailType.tp_init = (initproc)PyCoreTrail_init;
    CoreTrailType.tp_dealloc = (destructor)PyCoreTrail_dealloc;
    CoreTrailType.tp_new = PyType_GenericNew;
    if (PyType_Ready(&CoreTrailType) < 0) return NULL;

    PyObject* m = PyModule_Create(&module_def);
    if (m == NULL) return NULL;
    Py_INCREF(&CoreTrailType);
    if (PyModule_AddObject(m, "CoreTrail", (PyObject*)&CoreTrailType) < 0) {
        Py_DECREF(&CoreTrailType);
        Py_DECREF(m);
        return NULL;
    }
    return m;
}
