#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <memory>
#include <stdexcept>
#include <vector>
#include <cstdint>

#include "PBConfig.h"
#include "weightedlit.h"
#include "pbconstraint.h"
#include "auxvarmanager.h"
#include "VectorClauseDatabase.h"
#include "pb2cnf.h"

#ifndef HERMAX_PBLIB_ENABLE_PYINT_CACHE
#define HERMAX_PBLIB_ENABLE_PYINT_CACHE 1
#endif

#define PYINT_CACHE_SIZE (1u << 10)

typedef struct {
    int key;
    PyObject* obj;  // cache-owned reference
    unsigned char used;
} PyIntCacheEntry;

typedef struct {
    PyIntCacheEntry slots[PYINT_CACHE_SIZE];
    uint16_t used_idx[PYINT_CACHE_SIZE];
    size_t used_count;
} PyIntCache;

static inline uint32_t pyint_cache_hash(int v) {
    return ((uint32_t)v * 2654435761u) & (PYINT_CACHE_SIZE - 1u);
}

static PyObject* pyint_cache_get_or_make(PyIntCache* cache, int v) {
#if !HERMAX_PBLIB_ENABLE_PYINT_CACHE
    (void)cache;
    return PyLong_FromLong((long)v);
#else
    uint32_t idx = pyint_cache_hash(v);
    PyIntCacheEntry* e = &cache->slots[idx];
    if (e->used && e->key == v) {
        Py_INCREF(e->obj);
        return e->obj;
    }

    PyObject* obj = PyLong_FromLong((long)v);
    if (!obj) return nullptr;

    if (e->used) {
        Py_DECREF(e->obj);
    } else {
        cache->used_idx[cache->used_count++] = (uint16_t)idx;
    }

    e->used = 1;
    e->key = v;
    e->obj = obj;
    Py_INCREF(obj);  // caller ref
    return obj;
#endif
}

static void pyint_cache_clear(PyIntCache* cache) {
#if HERMAX_PBLIB_ENABLE_PYINT_CACHE
    for (size_t i = 0; i < cache->used_count; ++i) {
        PyIntCacheEntry* e = &cache->slots[cache->used_idx[i]];
        if (e->used) {
            Py_DECREF(e->obj);
            e->obj = nullptr;
            e->used = 0;
        }
    }
    cache->used_count = 0;
#else
    (void)cache;
#endif
}

struct PyIntCacheGuard {
    PyIntCache cache;
    PyIntCacheGuard() : cache{} {}
    ~PyIntCacheGuard() { pyint_cache_clear(&cache); }
};

static PyObject* py_encode_pb(PyObject*, PyObject* args, PyObject* kwargs) {
    PyObject* wlits_obj = nullptr;
    int comparator = 0;
    long long bound = 0;
    int top_id = 0;
    int pb_encoder = 0;
    PyObject* conditionals_obj = nullptr;

    static const char* kwlist[] = {
        "wlits", "comparator", "bound", "top_id", "pb_encoder", "conditionals", nullptr
    };

    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "OiLiiO",
            const_cast<char**>(kwlist),
            &wlits_obj,
            &comparator,
            &bound,
            &top_id,
            &pb_encoder,
            &conditionals_obj)) {
        return nullptr;
    }

    if (!PyList_Check(wlits_obj)) {
        PyErr_SetString(PyExc_TypeError, "wlits must be a list of (lit, weight) pairs");
        return nullptr;
    }

    if (conditionals_obj == Py_None) {
        conditionals_obj = PyList_New(0);
        if (!conditionals_obj) {
            return nullptr;
        }
    } else {
        Py_INCREF(conditionals_obj);
    }

    if (!PyList_Check(conditionals_obj)) {
        Py_DECREF(conditionals_obj);
        conditionals_obj = nullptr;
        PyErr_SetString(PyExc_TypeError, "conditionals must be a list of ints");
        return nullptr;
    }

    try {
        PyIntCacheGuard cache_guard;
        std::vector<PBLib::WeightedLit> wlits;
        wlits.reserve((size_t)PyList_GET_SIZE(wlits_obj));

        for (Py_ssize_t i = 0; i < PyList_GET_SIZE(wlits_obj); ++i) {
            PyObject* item = PyList_GET_ITEM(wlits_obj, i);  // borrowed
            if (!PyTuple_Check(item) || PyTuple_GET_SIZE(item) != 2) {
                Py_DECREF(conditionals_obj);
                PyErr_SetString(PyExc_TypeError, "each weighted literal must be a tuple (lit, weight)");
                return nullptr;
            }

            long lit = PyLong_AsLong(PyTuple_GET_ITEM(item, 0));
            if (PyErr_Occurred()) {
                Py_DECREF(conditionals_obj);
                return nullptr;
            }
            long long weight = PyLong_AsLongLong(PyTuple_GET_ITEM(item, 1));
            if (PyErr_Occurred()) {
                Py_DECREF(conditionals_obj);
                return nullptr;
            }

            wlits.emplace_back((int32_t)lit, (int64_t)weight);
        }

        PBLib::PBConstraint constr(wlits, static_cast<PBLib::Comparator>(comparator), (int64_t)bound);

        std::vector<int32_t> conditionals;
        conditionals.reserve((size_t)PyList_GET_SIZE(conditionals_obj));
        for (Py_ssize_t i = 0; i < PyList_GET_SIZE(conditionals_obj); ++i) {
            PyObject* lit_obj = PyList_GET_ITEM(conditionals_obj, i);  // borrowed
            long lit = PyLong_AsLong(lit_obj);
            if (PyErr_Occurred()) {
                Py_DECREF(conditionals_obj);
                return nullptr;
            }
            conditionals.push_back((int32_t)lit);
        }
        Py_DECREF(conditionals_obj);

        if (!conditionals.empty()) {
            constr.addConditionals(conditionals);
        }

        PBConfig config = std::make_shared<PBConfigClass>();
        config->pb_encoder = static_cast<PB_ENCODER::PB2CNF_PB_Encoder>(pb_encoder);

        VectorClauseDatabase result(config);
        AuxVarManager varmgr(top_id + 1);
        PB2CNF pb2cnf(config);
        pb2cnf.encode(constr, result, varmgr);

        const auto& clauses = result.getClauses();
        PyObject* py_clauses = PyList_New((Py_ssize_t)clauses.size());
        if (!py_clauses) {
            return nullptr;
        }

        for (Py_ssize_t i = 0; i < (Py_ssize_t)clauses.size(); ++i) {
            const auto& cl = clauses[(size_t)i];
            PyObject* py_clause = PyList_New((Py_ssize_t)cl.size());
            if (!py_clause) {
                Py_DECREF(py_clauses);
                return nullptr;
            }
            for (Py_ssize_t j = 0; j < (Py_ssize_t)cl.size(); ++j) {
                PyObject* lit = pyint_cache_get_or_make(&cache_guard.cache, (int)cl[(size_t)j]);
                if (!lit) {
                    Py_DECREF(py_clause);
                    Py_DECREF(py_clauses);
                    return nullptr;
                }
                PyList_SET_ITEM(py_clause, j, lit);  // steals
            }
            PyList_SET_ITEM(py_clauses, i, py_clause);  // steals
        }

        PyObject* py_aux = PyLong_FromLong((long)varmgr.getBiggestReturnedAuxVar());
        if (!py_aux) {
            Py_DECREF(py_clauses);
            return nullptr;
        }

        PyObject* out = PyTuple_New(2);
        if (!out) {
            Py_DECREF(py_aux);
            Py_DECREF(py_clauses);
            return nullptr;
        }
        PyTuple_SET_ITEM(out, 0, py_clauses);  // steals
        PyTuple_SET_ITEM(out, 1, py_aux);      // steals
        return out;
    } catch (const std::exception& e) {
        if (conditionals_obj) {
            Py_DECREF(conditionals_obj);
        }
        PyErr_SetString(PyExc_RuntimeError, e.what());
        return nullptr;
    } catch (...) {
        if (conditionals_obj) {
            Py_DECREF(conditionals_obj);
        }
        PyErr_SetString(PyExc_RuntimeError, "unknown error in pblib encoder");
        return nullptr;
    }
}

static PyMethodDef module_methods[] = {
    {
        "encode_pb",
        reinterpret_cast<PyCFunction>(py_encode_pb),
        METH_VARARGS | METH_KEYWORDS,
        "Encode one PB constraint into CNF clauses."
    },
    {nullptr, nullptr, 0, nullptr}
};

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    "_pblib",
    "Raw CPython bindings for PBLib",
    -1,
    module_methods,
    nullptr,
    nullptr,
    nullptr,
    nullptr
};

PyMODINIT_FUNC PyInit__pblib(void) {
    PyObject* m = PyModule_Create(&module_def);
    if (!m) {
        return nullptr;
    }

    if (PyModule_AddIntConstant(m, "PB_BEST", (int)PB_ENCODER::PB2CNF_PB_Encoder::BEST) < 0) return nullptr;
    if (PyModule_AddIntConstant(m, "PB_BDD", (int)PB_ENCODER::PB2CNF_PB_Encoder::BDD) < 0) return nullptr;
    if (PyModule_AddIntConstant(m, "PB_SWC", (int)PB_ENCODER::PB2CNF_PB_Encoder::SWC) < 0) return nullptr;
    if (PyModule_AddIntConstant(m, "PB_SORTINGNETWORKS", (int)PB_ENCODER::PB2CNF_PB_Encoder::SORTINGNETWORKS) < 0) return nullptr;
    if (PyModule_AddIntConstant(m, "PB_ADDER", (int)PB_ENCODER::PB2CNF_PB_Encoder::ADDER) < 0) return nullptr;
    if (PyModule_AddIntConstant(m, "PB_BINARY_MERGE", (int)PB_ENCODER::PB2CNF_PB_Encoder::BINARY_MERGE) < 0) return nullptr;

    if (PyModule_AddIntConstant(m, "LEQ", (int)PBLib::Comparator::LEQ) < 0) return nullptr;
    if (PyModule_AddIntConstant(m, "GEQ", (int)PBLib::Comparator::GEQ) < 0) return nullptr;
    if (PyModule_AddIntConstant(m, "BOTH", (int)PBLib::Comparator::BOTH) < 0) return nullptr;

    return m;
}
