#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <stdexcept>
#include <string_view>
#include <numeric>
#include <limits>
#include <algorithm>

#include "structuredpb/encoder.hpp"
#include "structuredpb/rggt_equality.hpp"

namespace {

bool divide_common_factor(structuredpb::GroupedLeqConstraint& constraint, bool equality) {
    structuredpb::Weight divisor = 0;
    for (const auto& term : constraint.terms) {
        divisor = std::gcd(divisor, term.weight);
        if (divisor == 1) {
            return true;
        }
    }
    if (divisor <= 1) {
        return true;
    }
    if (equality && constraint.bound % divisor != 0) {
        return false;
    }
    for (auto& term : constraint.terms) {
        term.weight /= divisor;
    }
    // All weights and the upper bound are unsigned. The equivalent bound
    // rounds down; AMO groups and literal IDs do not change.
    constraint.bound /= divisor;
    return true;
}

PyObject* py_encode_grouped(PyObject* args, PyObject* kwargs, bool equality) {
    PyObject* wlits_obj = nullptr;
    PyObject* groups_obj = nullptr;
    PyObject* bound_obj = nullptr;
    int top_id = 0;
    PyObject* encoder_obj = nullptr;
    int emit_amo = 1;

    static const char* kwlist[] = {"wlits", "groups", "bound", "top_id", "encoder", "emit_amo", nullptr};
    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "OOOiOp",
            const_cast<char**>(kwlist),
            &wlits_obj,
            &groups_obj,
            &bound_obj,
            &top_id,
            &encoder_obj,
            &emit_amo)) {
        return nullptr;
    }

    // Unlike the K parser format, this conversion rejects negative values
    // instead of silently wrapping them to an unsigned upper bound.
    const auto bound = PyLong_AsUnsignedLongLong(bound_obj);
    if (PyErr_Occurred()) {
        return nullptr;
    }
    if (top_id < 0 || top_id == std::numeric_limits<int>::max()) {
        PyErr_SetString(PyExc_ValueError, "top_id is outside the supported variable ID range");
        return nullptr;
    }

    if (!PyList_Check(wlits_obj)) {
        PyErr_SetString(PyExc_TypeError, "wlits must be a list of (lit, weight) pairs");
        return nullptr;
    }
    if (!PyList_Check(groups_obj)) {
        PyErr_SetString(PyExc_TypeError, "groups must be a list of literal lists");
        return nullptr;
    }

    const char* encoder_cstr = PyUnicode_AsUTF8(encoder_obj);
    if (encoder_cstr == nullptr) {
        return nullptr;
    }

    try {
        structuredpb::GroupedLeqConstraint constraint;
        constraint.bound = static_cast<structuredpb::Weight>(bound);
        constraint.emit_amo = emit_amo != 0;
        constraint.terms.reserve(static_cast<std::size_t>(PyList_GET_SIZE(wlits_obj)));
        constraint.groups.reserve(static_cast<std::size_t>(PyList_GET_SIZE(groups_obj)));

        for (Py_ssize_t i = 0; i < PyList_GET_SIZE(wlits_obj); ++i) {
            PyObject* item = PyList_GET_ITEM(wlits_obj, i);
            if (!PyTuple_Check(item) || PyTuple_GET_SIZE(item) != 2) {
                PyErr_SetString(PyExc_TypeError, "each weighted literal must be a tuple (lit, weight)");
                return nullptr;
            }
            long lit = PyLong_AsLong(PyTuple_GET_ITEM(item, 0));
            if (PyErr_Occurred()) {
                return nullptr;
            }
            if (lit <= -std::numeric_limits<int>::max() || lit >= std::numeric_limits<int>::max()) {
                PyErr_SetString(PyExc_ValueError, "literal ID is outside the supported range");
                return nullptr;
            }
            top_id = std::max(top_id, static_cast<int>(lit < 0 ? -lit : lit));
            unsigned long long weight = PyLong_AsUnsignedLongLong(PyTuple_GET_ITEM(item, 1));
            if (PyErr_Occurred()) {
                return nullptr;
            }
            constraint.terms.push_back(
                structuredpb::WeightedLiteral{static_cast<int>(lit), static_cast<structuredpb::Weight>(weight)});
        }

        for (Py_ssize_t i = 0; i < PyList_GET_SIZE(groups_obj); ++i) {
            PyObject* group_obj = PyList_GET_ITEM(groups_obj, i);
            if (!PyList_Check(group_obj)) {
                PyErr_SetString(PyExc_TypeError, "each group must be a list of literals");
                return nullptr;
            }
            std::vector<int> group;
            group.reserve(static_cast<std::size_t>(PyList_GET_SIZE(group_obj)));
            for (Py_ssize_t j = 0; j < PyList_GET_SIZE(group_obj); ++j) {
                long lit = PyLong_AsLong(PyList_GET_ITEM(group_obj, j));
                if (PyErr_Occurred()) {
                    return nullptr;
                }
                if (lit <= -std::numeric_limits<int>::max() || lit >= std::numeric_limits<int>::max()) {
                    PyErr_SetString(PyExc_ValueError, "literal ID is outside the supported range");
                    return nullptr;
                }
                group.push_back(static_cast<int>(lit));
            }
            constraint.groups.push_back(std::move(group));
        }

        structuredpb::EncodeOptions options;
        options.top_id = top_id;
        if (equality) {
            if (std::string_view(encoder_cstr) != "rggt") {
                throw std::invalid_argument("structuredpb: native equality is supported only by rggt");
            }
            constraint.validate();
        }
        structuredpb::EncodeResult result;
        if (!divide_common_factor(constraint, equality)) {
            result.cnf.num_vars = options.top_id;
            result.cnf.add_clause({});
        } else if (equality) {
            result = structuredpb::encode_rggt_equality(constraint, options);
        } else {
            auto encoder = structuredpb::make_encoder(std::string_view(encoder_cstr));
            result = encoder->encode(constraint, options);
        }

        PyObject* py_clauses = PyList_New(static_cast<Py_ssize_t>(result.cnf.clauses.size()));
        if (py_clauses == nullptr) {
            return nullptr;
        }
        for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(result.cnf.clauses.size()); ++i) {
            const auto& clause = result.cnf.clauses[static_cast<std::size_t>(i)];
            PyObject* py_clause = PyList_New(static_cast<Py_ssize_t>(clause.size()));
            if (py_clause == nullptr) {
                Py_DECREF(py_clauses);
                return nullptr;
            }
            for (Py_ssize_t j = 0; j < static_cast<Py_ssize_t>(clause.size()); ++j) {
                PyObject* lit_obj = PyLong_FromLong(static_cast<long>(clause[static_cast<std::size_t>(j)]));
                if (lit_obj == nullptr) {
                    Py_DECREF(py_clause);
                    Py_DECREF(py_clauses);
                    return nullptr;
                }
                PyList_SET_ITEM(py_clause, j, lit_obj);
            }
            PyList_SET_ITEM(py_clauses, i, py_clause);
        }

        PyObject* py_aux = PyLong_FromLong(static_cast<long>(result.cnf.num_vars));
        if (py_aux == nullptr) {
            Py_DECREF(py_clauses);
            return nullptr;
        }
        PyObject* out = PyTuple_New(2);
        if (out == nullptr) {
            Py_DECREF(py_clauses);
            Py_DECREF(py_aux);
            return nullptr;
        }
        PyTuple_SET_ITEM(out, 0, py_clauses);
        PyTuple_SET_ITEM(out, 1, py_aux);
        return out;
    } catch (const std::exception& exc) {
        PyErr_SetString(PyExc_RuntimeError, exc.what());
        return nullptr;
    } catch (...) {
        PyErr_SetString(PyExc_RuntimeError, "unknown error in structuredpb encoder");
        return nullptr;
    }
}

PyObject* py_encode_leq(PyObject*, PyObject* args, PyObject* kwargs) {
    return py_encode_grouped(args, kwargs, false);
}

PyObject* py_encode_eq(PyObject*, PyObject* args, PyObject* kwargs) {
    return py_encode_grouped(args, kwargs, true);
}

PyObject* py_available_encoders(PyObject*, PyObject*) {
    try {
        const auto names = structuredpb::available_encoders();
        PyObject* out = PyList_New(static_cast<Py_ssize_t>(names.size()));
        if (out == nullptr) {
            return nullptr;
        }
        for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(names.size()); ++i) {
            PyObject* name = PyUnicode_FromString(names[static_cast<std::size_t>(i)].c_str());
            if (name == nullptr) {
                Py_DECREF(out);
                return nullptr;
            }
            PyList_SET_ITEM(out, i, name);
        }
        return out;
    } catch (const std::exception& exc) {
        PyErr_SetString(PyExc_RuntimeError, exc.what());
        return nullptr;
    }
}

PyMethodDef module_methods[] = {
    {"encode_leq", reinterpret_cast<PyCFunction>(py_encode_leq), METH_VARARGS | METH_KEYWORDS,
     "Encode one grouped <= pseudo-Boolean constraint."},
    {"encode_eq", reinterpret_cast<PyCFunction>(py_encode_eq), METH_VARARGS | METH_KEYWORDS,
     "Encode one grouped equality with a shared sum tree."},
    {"available_encoders", py_available_encoders, METH_NOARGS, "Return the list of encoder names."},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    "_pbamo",
    "PBAMO structured pseudo-Boolean encoders for Hermax",
    -1,
    module_methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__pbamo(void) {
    PyObject* m = PyModule_Create(&module_def);
    if (!m) {
        return nullptr;
    }
    if (PyModule_AddStringConstant(m, "ENC_MDD", "mdd") < 0) {
        Py_DECREF(m);
        return nullptr;
    }
    if (PyModule_AddStringConstant(m, "ENC_GSWC", "gswc") < 0) {
        Py_DECREF(m);
        return nullptr;
    }
    if (PyModule_AddStringConstant(m, "ENC_GGPW", "ggpw") < 0) {
        Py_DECREF(m);
        return nullptr;
    }
    if (PyModule_AddStringConstant(m, "ENC_GMTO", "gmto") < 0) {
        Py_DECREF(m);
        return nullptr;
    }
    if (PyModule_AddStringConstant(m, "ENC_RGGT", "rggt") < 0) {
        Py_DECREF(m);
        return nullptr;
    }
    return m;
}
