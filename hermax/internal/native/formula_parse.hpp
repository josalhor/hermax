#ifndef HERMAX_FORMULA_PARSE_HPP
#define HERMAX_FORMULA_PARSE_HPP

#include <Python.h>
#include <cstddef>
#include <cstdint>

namespace hermax::formula {

// Private storage operations keep the parser independent of Python storage types.
struct ClauseBuilder {
    PyObject *(*create)();
    int (*append)(PyObject *, PyObject *);
    int (*append_narrow)(PyObject *, const int32_t *, size_t);
    PyObject *(*max_var)(PyObject *);
};

PyObject *parse(PyObject *args, const ClauseBuilder &storage);

} // namespace hermax::formula
#endif
