#ifndef HERMAX_CLAUSE_READ_API_HPP
#define HERMAX_CLAUSE_READ_API_HPP

#include <Python.h>
#include <cstddef>
#include <cstdint>

namespace hermax::clauses {

// Independent of the write API and PackedClauses' C++ layout. The GIL must be
// held. Each row pointer is borrowed for the duration of the callback only.
// Callbacks return 0 on success, -1 with a Python error on failure, and must not
// throw C++ exceptions. A retained storage snapshot keeps rows alive even if a
// callback causes the original storage to be mutated through another reference.
struct ReadAPI {
    unsigned version;
    int (*visit)(PyObject *, void *, int (*)(void *, const int32_t *, size_t));
};

inline const ReadAPI *import_read_api() {
    auto *api = static_cast<const ReadAPI *>(
        PyCapsule_Import("hermax.internal._clauses._READ_API", 0));
    if (api && api->version != 1) {
        PyErr_SetString(PyExc_ImportError, "Incompatible native clause read API.");
        return nullptr;
    }
    return api;
}

} // namespace hermax::clauses
#endif
