#ifndef HERMAX_CLAUSE_API_HPP
#define HERMAX_CLAUSE_API_HPP

#include <Python.h>
#include "packed_clauses.hpp"

namespace hermax::clauses {

struct API {
    unsigned version;
    size_t buffer_size;
    PyObject *(*create)();
    int (*append)(PyObject *, const int32_t *, size_t);
    PyObject *(*adopt)(PackedClauses *);
};

inline const API *import_api() {
    auto *api = static_cast<const API *>(PyCapsule_Import("hermax.internal._clauses._C_API", 0));
    if (api && (api->version != 1 || api->buffer_size != sizeof(PackedClauses))) {
        PyErr_SetString(PyExc_ImportError, "Incompatible internal clause storage API.");
        return nullptr;
    }
    return api;
}

} // namespace hermax::clauses
#endif
