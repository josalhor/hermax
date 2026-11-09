#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <climits>
#include <cstdint>
#include <exception>
#include <limits>
#include <stdexcept>
#include <unordered_set>
#include <vector>
#include "order_sum.hpp"
#include "pb_budget.hpp"
#include "pb2cnf.h"
#include "native/clause_api.hpp"
using integer_sum::Chains;
static PyObject *BudgetError = nullptr;

static int64_t integer(PyObject *o, const char *label) {
    if (!PyLong_Check(o) || PyBool_Check(o)) {
        PyErr_Format(PyExc_TypeError, "%s must be an integer", label);
        throw 0;
    }
    long long v = PyLong_AsLongLong(o);
    if (v == -1 && PyErr_Occurred())
        throw 0;
    return v;
}
static int small_integer(PyObject *o, const char *label) {
    int64_t v = integer(o, label);
    if (v < INT_MIN || v > INT_MAX) {
        PyErr_Format(PyExc_OverflowError, "%s", label);
        throw 0;
    }
    return static_cast<int>(v);
}
static int literal(PyObject *o) {
    int v = small_integer(o, "literal");
    if (!v || v == INT_MIN) {
        PyErr_SetString(PyExc_ValueError, "invalid literal");
        throw 0;
    }
    return v;
}
static std::vector<int64_t> int_vector(PyObject *iterable, const char *msg, const char *label) {
    PyObject *seq = PySequence_Fast(iterable, msg);
    if (!seq)
        throw 0;
    std::vector<int64_t> out;
    try {
        const Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
        out.reserve(n);
        for (Py_ssize_t i = 0; i < n; ++i)
            out.push_back(integer(PySequence_Fast_GET_ITEM(seq, i), label));
    } catch (...) {
        Py_DECREF(seq);
        throw;
    }
    Py_DECREF(seq);
    return out;
}

static void translate() {
    try {
        throw;
    } catch (int) {
    } catch (const integer_sum::BudgetExceeded &e) {
        if (BudgetError)
            PyErr_SetString(BudgetError, e.what());
        else
            PyErr_SetString(PyExc_RuntimeError, e.what());
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
static PyObject *output_clauses(integer_sum::Cnf &cnf, const hermax::clauses::API *api) {
    if (api) {
        PyObject *r = api->adopt(&cnf.clauses);
        if (!r)
            throw 0;
        return r;
    }
    PyObject *list = PyList_New(cnf.clauses.size());
    if (!list)
        throw 0;
    for (size_t i = 0; i < cnf.clauses.size(); ++i) {
        auto row = cnf.clauses[i];
        PyObject *cl = PyList_New(row.size());
        if (!cl) {
            Py_DECREF(list);
            throw 0;
        }
        for (size_t j = 0; j < row.size(); ++j) {
            PyObject *x = PyLong_FromLong(row[j]);
            if (!x) {
                Py_DECREF(cl);
                Py_DECREF(list);
                throw 0;
            }
            PyList_SET_ITEM(cl, j, x);
        }
        PyList_SET_ITEM(list, i, cl);
    }
    return list;
}
template <bool Packed>
static PyObject *encode_order_sum(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {"chains", "bound", "top_id", "mode", "modulus", nullptr};
    PyObject *groups, *bv, *tv, *mv = nullptr, *modv = nullptr;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OOO|OO:encode_order_sum",
                                     const_cast<char **>(names), &groups, &bv, &tv, &mv, &modv))
        return nullptr;
    try {
        int top = small_integer(tv, "top_id"), bound = small_integer(bv, "bound"),
            mode = mv ? small_integer(mv, "mode") : 0,
            mod = modv ? small_integer(modv, "modulus") : 0;
        if (top < 0 || mode < 0 || mode > 1 || mod < 0 || mod == 1) {
            PyErr_SetString(PyExc_ValueError, "invalid order-sum configuration");
            throw 0;
        }
        Chains chains;
        std::unordered_set<int> seen;
        int64_t total = 0;
        PyObject *outer = PyObject_GetIter(groups);
        if (!outer)
            throw 0;
        PyObject *group;
        while ((group = PyIter_Next(outer))) {
            PyObject *inner = PyObject_GetIter(group);
            Py_DECREF(group);
            if (!inner) {
                Py_DECREF(outer);
                throw 0;
            }
            std::vector<int> row;
            PyObject *item;
            while ((item = PyIter_Next(inner))) {
                int lit;
                try {
                    lit = literal(item);
                } catch (...) {
                    Py_DECREF(item);
                    Py_DECREF(inner);
                    Py_DECREF(outer);
                    throw;
                }
                Py_DECREF(item);
                if (!seen.insert(std::abs(lit)).second) {
                    Py_DECREF(inner);
                    Py_DECREF(outer);
                    PyErr_SetString(PyExc_ValueError, "threshold chains must be disjoint");
                    throw 0;
                }
                top = std::max(top, std::abs(lit));
                row.push_back(lit);
                if (++total > INT_MAX) {
                    Py_DECREF(inner);
                    Py_DECREF(outer);
                    PyErr_SetString(PyExc_OverflowError, "order sum is too large");
                    throw 0;
                }
            }
            Py_DECREF(inner);
            if (PyErr_Occurred()) {
                Py_DECREF(outer);
                throw 0;
            }
            if (!row.empty())
                chains.push_back(std::move(row));
        }
        Py_DECREF(outer);
        if (PyErr_Occurred())
            throw 0;
        const auto *api = Packed ? hermax::clauses::import_api() : nullptr;
        if (Packed && !api)
            throw 0;
        integer_sum::Cnf cnf(Packed ? hermax::clauses::Memory{PyMem_Malloc, PyMem_Free}
                                    : hermax::clauses::Memory{});
        integer_sum::encode(chains, bound, mode, mod, top, cnf);
        if (PyErr_CheckSignals() < 0)
            throw 0;
        PyObject *clauses = output_clauses(cnf, api);
        if (!clauses)
            throw 0;
        return Py_BuildValue("(Ni)", clauses, top);
    } catch (...) {
        if (!PyErr_Occurred())
            translate();
        return nullptr;
    }
}
static PyObject *assess_order_sum(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {"values", "bound", nullptr};
    PyObject *values, *bv;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO:assess_order_sum",
                                     const_cast<char **>(names), &values, &bv))
        return nullptr;
    try {
        int bound = small_integer(bv, "bound");
        PyObject *iter = PyObject_GetIter(values);
        if (!iter)
            throw 0;
        std::vector<size_t> widths;
        int64_t total = 0;
        PyObject *x;
        while ((x = PyIter_Next(iter))) {
            int w;
            try {
                w = small_integer(x, "width");
            } catch (...) {
                Py_DECREF(x);
                Py_DECREF(iter);
                throw;
            }
            Py_DECREF(x);
            if (w < 0) {
                Py_DECREF(iter);
                PyErr_SetString(PyExc_ValueError, "width must be nonnegative");
                throw 0;
            }
            if ((total += w) > INT_MAX) {
                Py_DECREF(iter);
                PyErr_SetString(PyExc_OverflowError, "order sum is too large");
                throw 0;
            }
            if (w)
                widths.push_back(w);
        }
        Py_DECREF(iter);
        if (PyErr_Occurred())
            throw 0;
        auto p = integer_sum::assess(widths, bound);
        PyObject *d = PyDict_New();
        if (!d)
            throw 0;
        const char *keys[] = {"leaf_variables", "leaf_clauses", "whole_variables", "whole_clauses",
                              "modulus"};
        uint64_t vals[] = {p.leaf.variables, p.leaf.clauses, p.whole.variables, p.whole.clauses,
                           p.modulus};
        for (int i = 0; i < 5; ++i) {
            PyObject *v = PyLong_FromUnsignedLongLong(vals[i]);
            if (!v || PyDict_SetItemString(d, keys[i], v) < 0) {
                Py_XDECREF(v);
                Py_DECREF(d);
                throw 0;
            }
            Py_DECREF(v);
        }
        return d;
    } catch (...) {
        if (!PyErr_Occurred())
            translate();
        return nullptr;
    }
}
template <bool Packed> static PyObject *encode_pb(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {"wlits",       "comparator",   "bound",
                                  "top_id",      "pb_encoder",   "conditionals",
                                  "state_limit", "clause_limit", nullptr};
    PyObject *pairs, *comp_o, *bound_o, *top_o, *enc_o, *conds, *state_o = nullptr,
                                                                *clause_o = nullptr;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OOOOOO|OO:encode_pb",
                                     const_cast<char **>(names), &pairs, &comp_o, &bound_o, &top_o,
                                     &enc_o, &conds, &state_o, &clause_o))
        return nullptr;
    try {
        int comparator = small_integer(comp_o, "comparator"), top = small_integer(top_o, "top_id"),
            encoder = small_integer(enc_o, "pb_encoder");
        int64_t bound = integer(bound_o, "bound"),
                state = state_o ? integer(state_o, "state_limit") : 0,
                clause_limit = clause_o ? integer(clause_o, "clause_limit") : 0;
        if (state < 0 || clause_limit < 0 || top < 0) {
            PyErr_SetString(PyExc_ValueError, "limits and top_id must be nonnegative");
            throw 0;
        }
        if (comparator != PBLib::LEQ && comparator != PBLib::GEQ && comparator != PBLib::BOTH) {
            PyErr_SetString(PyExc_ValueError, "invalid comparator");
            throw 0;
        }
        if (encoder < 0 || encoder > 7 || encoder == 6) {
            PyErr_SetString(PyExc_ValueError, "invalid encoder");
            throw 0;
        }
        std::vector<PBLib::WeightedLit> terms;
        std::vector<int64_t> weights;
        std::unordered_set<int> seen;
        PyObject *iter = PyObject_GetIter(pairs);
        if (!iter)
            throw 0;
        PyObject *pair;
        while ((pair = PyIter_Next(iter))) {
            PyObject *entry = PySequence_Fast(pair, "expected a literal and weight");
            Py_DECREF(pair);
            if (!entry) {
                Py_DECREF(iter);
                throw 0;
            }
            if (PySequence_Fast_GET_SIZE(entry) != 2) {
                Py_DECREF(entry);
                Py_DECREF(iter);
                PyErr_SetString(PyExc_ValueError, "expected a literal and weight");
                throw 0;
            }
            int lit = literal(PySequence_Fast_GET_ITEM(entry, 0));
            int64_t weight = integer(PySequence_Fast_GET_ITEM(entry, 1), "weight");
            Py_DECREF(entry);
            if (weight <= 0 || !seen.insert(std::abs(lit)).second) {
                Py_DECREF(iter);
                PyErr_SetString(PyExc_ValueError,
                                "expected distinct literals with positive weights");
                throw 0;
            }
            terms.emplace_back(lit, weight);
            weights.push_back(weight);
            top = std::max(top, std::abs(lit));
        }
        Py_DECREF(iter);
        if (PyErr_Occurred())
            throw 0;
        integer_sum::total_weight(weights);
        if (state)
            integer_sum::count_states(weights, bound, static_cast<PBLib::Comparator>(comparator),
                                      state);
        PBLib::PBConstraint constraint(terms, static_cast<PBLib::Comparator>(comparator), bound);
        std::vector<int32_t> guards;
        iter = PyObject_GetIter(conds);
        if (!iter)
            throw 0;
        while ((pair = PyIter_Next(iter))) {
            int lit;
            try {
                lit = literal(pair);
            } catch (...) {
                Py_DECREF(pair);
                Py_DECREF(iter);
                throw;
            }
            Py_DECREF(pair);
            guards.push_back(lit);
            top = std::max(top, std::abs(lit));
        }
        Py_DECREF(iter);
        if (PyErr_Occurred())
            throw 0;
        constraint.addConditionals(guards);
        if (top == INT_MAX) {
            PyErr_SetString(PyExc_OverflowError, "variable IDs exhausted");
            throw 0;
        }
        PBConfig config = std::make_shared<PBConfigClass>();
        config->pb_encoder = static_cast<PB_ENCODER::PB2CNF_PB_Encoder>(encoder == 7 ? 5 : encoder);
        if (encoder == 7) {
            config->use_watch_dog_encoding_in_binary_merger = true;
            config->use_gac_binary_merge = true;
        }
        const auto *api = Packed ? hermax::clauses::import_api() : nullptr;
        if (Packed && !api)
            throw 0;
        integer_sum::ClauseSink sink(config, clause_limit,
                                     Packed ? hermax::clauses::Memory{PyMem_Malloc, PyMem_Free}
                                            : hermax::clauses::Memory{});
        AuxVarManager variables(top + 1);
        PB2CNF compiler(config);
        compiler.encode(constraint, sink, variables);
        if (PyErr_CheckSignals() < 0)
            throw 0;
        PyObject *clauses = output_clauses(sink, api);
        if (!clauses)
            throw 0;
        PyObject *last = PyLong_FromLong(std::max(top, variables.getBiggestReturnedAuxVar()));
        if (!last) {
            Py_DECREF(clauses);
            throw 0;
        }
        PyObject *result = PyTuple_Pack(2, clauses, last);
        Py_DECREF(clauses);
        Py_DECREF(last);
        return result;
    } catch (...) {
        if (!PyErr_Occurred())
            translate();
        return nullptr;
    }
}
static PyObject *count_states(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char *names[] = {"weights", "bound", "comparator", "limit", nullptr};
    PyObject *w, *b, *c, *l = nullptr;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OOO|O:count_states", const_cast<char **>(names),
                                     &w, &b, &c, &l))
        return nullptr;
    try {
        auto weights = int_vector(w, "weights must be an iterable of integers", "weight");
        int64_t bound = integer(b, "bound");
        int comparator = small_integer(c, "comparator");
        int64_t limit = l ? integer(l, "limit") : 20000;
        if (limit < 0 ||
            (comparator != PBLib::LEQ && comparator != PBLib::GEQ && comparator != PBLib::BOTH)) {
            PyErr_SetString(PyExc_ValueError, "invalid state counter configuration");
            throw 0;
        }
        return PyLong_FromLongLong(integer_sum::count_states(
            std::move(weights), bound, static_cast<PBLib::Comparator>(comparator), limit));
    } catch (...) {
        if (!PyErr_Occurred())
            translate();
        return nullptr;
    }
}
static PyMethodDef methods[] = {
    {"encode_order_sum", (PyCFunction)(void (*)(void))encode_order_sum<false>,
     METH_VARARGS | METH_KEYWORDS, nullptr},
    {"_encode_order_sum_packed", (PyCFunction)(void (*)(void))encode_order_sum<true>,
     METH_VARARGS | METH_KEYWORDS, nullptr},
    {"assess_order_sum", (PyCFunction)(void (*)(void))assess_order_sum,
     METH_VARARGS | METH_KEYWORDS, nullptr},
    {"count_states", (PyCFunction)(void (*)(void))count_states, METH_VARARGS | METH_KEYWORDS,
     nullptr},
    {"encode_pb", (PyCFunction)(void (*)(void))encode_pb<false>, METH_VARARGS | METH_KEYWORDS,
     nullptr},
    {"_encode_pb_packed", (PyCFunction)(void (*)(void))encode_pb<true>,
     METH_VARARGS | METH_KEYWORDS, nullptr},
    {nullptr, nullptr, 0, nullptr}};
static PyModuleDef module = {PyModuleDef_HEAD_INIT, "_integer_sum_native",
                             "Native integer-sum and pseudo-Boolean encoders", -1, methods};
PyMODINIT_FUNC PyInit__integer_sum_native() {
    PyObject *m = PyModule_Create(&module);
    if (!m)
        return nullptr;
    BudgetError = PyErr_NewException("_integer_sum_native.EncodingBudgetExceeded",
                                     PyExc_RuntimeError, nullptr);
    if (!BudgetError || PyModule_AddObject(m, "EncodingBudgetExceeded", BudgetError) < 0) {
        Py_XDECREF(BudgetError);
        Py_DECREF(m);
        return nullptr;
    }
    Py_INCREF(BudgetError);
    struct {
        const char *name;
        int value;
    } constants[] = {
        {"LEQ", PBLib::LEQ},    {"GEQ", PBLib::GEQ}, {"BOTH", PBLib::BOTH},     {"PB_BEST", 0},
        {"PB_BDD", 1},          {"PB_SWC", 2},       {"PB_SORTINGNETWORKS", 3}, {"PB_ADDER", 4},
        {"PB_BINARY_MERGE", 5}, {"PB_LPW", 7}};
    for (auto c : constants)
        if (PyModule_AddIntConstant(m, c.name, c.value) < 0) {
            Py_DECREF(m);
            return nullptr;
        }
    return m;
}
