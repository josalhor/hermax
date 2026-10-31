#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <cstdint>
#include <map>
#include <memory>
#include <new>
#include <stdexcept>
#include <utility>
#include <vector>
#include "native/clause_api.hpp"

namespace {

struct Decref {
    void operator()(PyObject *value) const { Py_XDECREF(value); }
};
using Ref = std::unique_ptr<PyObject, Decref>;

using hermax::clauses::PackedClauses;
template <typename T> using Allocator = hermax::clauses::Allocator<T>;
const hermax::clauses::Memory python_memory{PyMem_Malloc, PyMem_Free};

Ref literal(PyObject *value) {
    if (PyBool_Check(value)) {
        PyErr_SetString(PyExc_TypeError, "DIMACS literals must be integers.");
        return {};
    }
    Ref result(PyNumber_Index(value));
    if (!result) return {};
    if (!PyObject_IsTrue(result.get())) {
        PyErr_SetString(PyExc_ValueError, "DIMACS literals cannot be 0.");
        return {};
    }
    return result;
}

Ref clause_sequence(PyObject *row) {
    if (PyTuple_Check(row) || PyList_Check(row)) return Ref(Py_NewRef(row));
    Ref dims(PyObject_GetAttrString(row, "dimacs"));
    if (!dims) {
        if (!PyErr_ExceptionMatches(PyExc_AttributeError)) return {};
        PyErr_Clear();
    }
    return Ref(PySequence_Fast(dims ? dims.get() : row, "Expected a DIMACS clause."));
}

Ref prepare_clause(PyObject *row) {
    Ref seq = clause_sequence(row);
    if (!seq) return {};
    // Conversions may execute Python code. Freeze the input before calling them.
    Ref source(PyTuple_Check(seq.get())
        ? PyTuple_GetSlice(seq.get(), 0, PyTuple_GET_SIZE(seq.get()))
        : PyList_AsTuple(seq.get()));
    if (!source) return {};
    Py_ssize_t size = PyTuple_GET_SIZE(source.get());
    bool canonical = true;
    for (Py_ssize_t i = 0; i < size; ++i) {
        PyObject *value = PyTuple_GET_ITEM(source.get(), i);
        if (!PyLong_CheckExact(value)) {
            canonical = false;
            break;
        }
        if (!PyObject_IsTrue(value)) {
            PyErr_SetString(PyExc_ValueError, "DIMACS literals cannot be 0.");
            return {};
        }
    }
    if (canonical) return source;
    Ref result(PyTuple_New(size));
    if (!result) return {};
    for (Py_ssize_t i = 0; i < size; ++i) {
        Ref value = literal(PyTuple_GET_ITEM(source.get(), i));
        if (!value) return {};
        PyTuple_SET_ITEM(result.get(), i, value.release());
    }
    return result;
}

struct Data : PackedClauses {
    using WideEntry = std::pair<const size_t, PyObject *>;
    std::map<size_t, PyObject *, std::less<size_t>, Allocator<WideEntry>> wide{Allocator<WideEntry>(python_memory)};

    Data() : PackedClauses(python_memory) {}
    explicit Data(PackedClauses &&buffer) : PackedClauses(std::move(buffer)) {
        if (ends.empty()) ends.push_back(0);
    }
    Data(const Data &other) : PackedClauses(other), wide(other.wide) {
        for (const auto &entry : wide) Py_INCREF(entry.second);
    }
    ~Data() { for (const auto &entry : wide) Py_DECREF(entry.second); }

    void truncate(size_t count) noexcept {
        auto first = wide.lower_bound(count);
        for (auto it = first; it != wide.end(); ++it) Py_DECREF(it->second);
        wide.erase(first, wide.end());
        literals.resize(ends[count]);
        ends.resize(count + 1);
    }

    struct Rollback {
        Data &data;
        size_t count;
        bool committed = false;
        explicit Rollback(Data &data) : data(data), count(data.size()) {}
        ~Rollback() { if (!committed) data.truncate(count); }
    };

    int append(PyObject *seq) {
        Rollback rollback(*this);
        bool needs_wide = false;
        Py_ssize_t length = PySequence_Fast_GET_SIZE(seq);
        for (Py_ssize_t i = 0; i < length; ++i) {
            PyObject *item = PySequence_Fast_GET_ITEM(seq, i);
            int overflow = 0;
            long value = PyLong_AsLongAndOverflow(item, &overflow);
            if (PyErr_Occurred()) return -1;
            if (overflow || value < -INT32_MAX || value > INT32_MAX) {
                needs_wide = true;
                break;
            }
            if (!value) {
                PyErr_SetString(PyExc_ValueError, "DIMACS literals cannot be 0.");
                return -1;
            }
            literals.push_back(static_cast<int32_t>(value));
        }
        if (needs_wide) {
            literals.resize(ends.back());
            wide.emplace(size(), seq);
            Py_INCREF(seq);
        }
        ends.push_back(literals.size());
        rollback.committed = true;
        return 0;
    }

    void extend(const Data &other, size_t first = 0) {
        Rollback rollback(*this);
        size_t first_row = size(), offset = literals.size();
        size_t begin = other.ends[first];
        literals.insert(literals.end(), other.literals.begin() + begin, other.literals.end());
        for (size_t i = first + 1; i < other.ends.size(); ++i) ends.push_back(offset + other.ends[i] - begin);
        for (auto it = other.wide.lower_bound(first); it != other.wide.end(); ++it) {
            wide.emplace(first_row + it->first - first, it->second);
            Py_INCREF(it->second);
        }
        rollback.committed = true;
    }

    void append_row(const Data &other, size_t row) {
        size_t first = other.ends[row], last = other.ends[row + 1];
        auto special = other.wide.find(row);
        if (special != other.wide.end()) {
            wide.emplace(size(), special->second);
            Py_INCREF(special->second);
        }
        literals.insert(literals.end(), other.literals.begin() + first, other.literals.begin() + last);
        ends.push_back(literals.size());
    }

    PyObject *row(size_t index) const {
        auto special = wide.find(index);
        if (special != wide.end()) return Py_NewRef(special->second);
        size_t first = ends[index], last = ends[index + 1];
        Ref result(PyTuple_New(last - first));
        if (!result) return nullptr;
        for (size_t j = first; j < last; ++j) {
            PyObject *value = PyLong_FromLong(literals[j]);
            if (!value) return nullptr;
            PyTuple_SET_ITEM(result.get(), j - first, value);
        }
        return result.release();
    }

    int32_t maximum() const {
        int32_t result = 0;
        for (auto value : literals) result = std::max(result, value < 0 ? -value : value);
        return result;
    }

    PyObject *max_var(int32_t maximum) const {
        Ref result(PyLong_FromLong(maximum));
        if (!result) return nullptr;
        for (const auto &entry : wide) {
            for (Py_ssize_t i = 0; i < PyTuple_GET_SIZE(entry.second); ++i) {
                Ref value(PyNumber_Absolute(PyTuple_GET_ITEM(entry.second, i)));
                if (!value) return nullptr;
                int greater = PyObject_RichCompareBool(value.get(), result.get(), Py_GT);
                if (greater < 0) return nullptr;
                if (greater) result = std::move(value);
            }
        }
        return result.release();
    }

    PyObject *to_lists(int32_t maximum) const {
        // Intern only when the lookup table is bounded by the literal count.
        size_t entries = 2 * (static_cast<uint64_t>(maximum) + 1);
        std::vector<PyObject *, Allocator<PyObject *>> objects{Allocator<PyObject *>(python_memory)};
        if (entries <= literals.size()) objects.resize(entries, nullptr);
        Ref result(PyList_New(size()));
        if (!result) return nullptr;
        for (size_t i = 0; i < size(); ++i) {
            auto special = wide.find(i);
            if (special != wide.end()) {
                PyObject *row = PySequence_List(special->second);
                if (!row) return nullptr;
                PyList_SET_ITEM(result.get(), i, row);
                continue;
            }
            size_t first = ends[i], last = ends[i + 1];
            PyObject *row = PyList_New(last - first);
            if (!row) return nullptr;
            PyList_SET_ITEM(result.get(), i, row);
            for (size_t j = first; j < last; ++j) {
                int32_t number = literals[j];
                size_t key = 2 * static_cast<uint64_t>(number < 0 ? -number : number) + (number < 0);
                PyObject *value;
                if (!objects.empty() && objects[key]) value = Py_NewRef(objects[key]);
                else {
                    value = PyLong_FromLong(number);
                    if (!value) return nullptr;
                    if (!objects.empty()) objects[key] = value;
                }
                PyList_SET_ITEM(row, j - first, value);
            }
        }
        return result.release();
    }
};

using SharedData = std::shared_ptr<Data>;
SharedData empty_data() { return std::allocate_shared<Data>(Allocator<Data>(python_memory)); }
struct Storage { PyObject_HEAD SharedData data; };
struct Iterator { PyObject_HEAD SharedData data; size_t index; };
PyTypeObject StorageType = {PyVarObject_HEAD_INIT(nullptr, 0)};
PyTypeObject IteratorType = {PyVarObject_HEAD_INIT(nullptr, 0)};

template <typename Function> PyObject *checked(Function function) noexcept {
    try { return function(); }
    catch (const std::bad_alloc &) { return PyErr_NoMemory(); }
    catch (const std::length_error &) { return PyErr_NoMemory(); }
}

Data &writable(Storage *self) {
    if (!self->data.unique()) self->data = std::allocate_shared<Data>(Allocator<Data>(python_memory), *self->data);
    return *self->data;
}

PyObject *wrap(PyTypeObject *type, SharedData data) {
    auto *self = reinterpret_cast<Storage *>(type->tp_alloc(type, 0));
    if (!self) return nullptr;
    new (&self->data) SharedData(std::move(data));
    return reinterpret_cast<PyObject *>(self);
}

int extend(Storage *self, PyObject *rows) {
    Ref iterator(PyObject_GetIter(rows));
    if (!iterator) return -1;
    if (PyObject_TypeCheck(iterator.get(), &IteratorType)) {
        auto *input = reinterpret_cast<Iterator *>(iterator.get());
        SharedData source = input->data;
        size_t first = std::min(input->index, source->size());
        if (!first && !self->data->size()) self->data = source;
        else writable(self).extend(*source, first);
        input->index = source->size();
        return 0;
    }
    while (Ref row{PyIter_Next(iterator.get())}) {
        Ref prepared = prepare_clause(row.get());
        if (!prepared || writable(self).append(prepared.get())) return -1;
    }
    return PyErr_Occurred() ? -1 : 0;
}

PyObject *storage_new(PyTypeObject *type, PyObject *args, PyObject *kwargs) {
    return checked([&]() -> PyObject * {
        PyObject *rows = nullptr;
        static const char *names[] = {"clauses", nullptr};
        if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|O", const_cast<char **>(names), &rows)) return nullptr;
        if (rows && PyObject_TypeCheck(rows, &StorageType)) return wrap(type, reinterpret_cast<Storage *>(rows)->data);
        Ref self(wrap(type, empty_data()));
        if (!self) return nullptr;
        if (rows && extend(reinterpret_cast<Storage *>(self.get()), rows)) return nullptr;
        return self.release();
    });
}

void storage_dealloc(Storage *self) {
    self->data.~SharedData();
    Py_TYPE(self)->tp_free(reinterpret_cast<PyObject *>(self));
}

Py_ssize_t storage_length(Storage *self) { return self->data->size(); }

PyObject *storage_append(Storage *self, PyObject *row) {
    return checked([&]() -> PyObject * {
        Ref prepared = prepare_clause(row);
        if (!prepared || writable(self).append(prepared.get())) return nullptr;
        Py_RETURN_NONE;
    });
}

PyObject *storage_extend(Storage *self, PyObject *rows) {
    return checked([&]() -> PyObject * {
        if (extend(self, rows)) return nullptr;
        Py_RETURN_NONE;
    });
}

PyObject *storage_get(Storage *self, PyObject *index) {
    if (PySlice_Check(index)) {
        Py_ssize_t first, last, step, count;
        if (PySlice_Unpack(index, &first, &last, &step)) return nullptr;
        SharedData source = self->data;
        count = PySlice_AdjustIndices(source->size(), &first, &last, step);
        Ref result(PyList_New(count));
        if (!result) return nullptr;
        for (Py_ssize_t i = 0; i < count; ++i) {
            PyObject *row = source->row(first + i * step);
            if (!row) return nullptr;
            PyList_SET_ITEM(result.get(), i, row);
        }
        return result.release();
    }
    Py_ssize_t i = PyNumber_AsSsize_t(index, PyExc_IndexError);
    if (i == -1 && PyErr_Occurred()) return nullptr;
    SharedData source = self->data;
    Py_ssize_t size = source->size();
    if (i < 0) i += size;
    if (i < 0 || i >= size) { PyErr_SetNone(PyExc_IndexError); return nullptr; }
    return source->row(i);
}

int storage_delete(Storage *self, PyObject *index, PyObject *value) {
    Ref result(checked([&]() -> PyObject * {
        if (value) { PyErr_SetString(PyExc_TypeError, "Clause assignment is not supported."); return nullptr; }
        Py_ssize_t first, last, step, count;
        bool slice = PySlice_Check(index);
        if (slice) {
            if (PySlice_Unpack(index, &first, &last, &step)) return nullptr;
        } else {
            first = PyNumber_AsSsize_t(index, PyExc_IndexError);
            if (first == -1 && PyErr_Occurred()) return nullptr;
        }
        Py_ssize_t size = storage_length(self);
        if (slice) count = PySlice_AdjustIndices(size, &first, &last, step);
        else {
            if (first < 0) first += size;
            if (first < 0 || first >= size) { PyErr_SetNone(PyExc_IndexError); return nullptr; }
            last = first + 1; step = 1; count = 1;
        }
        if (!count) Py_RETURN_NONE;
        if (step == 1 && last == size) writable(self).truncate(first);
        else {
            SharedData result = empty_data();
            for (Py_ssize_t i = 0; i < size; ++i) {
                bool remove = step > 0 ? (i >= first && i < last && (i - first) % step == 0)
                                       : (i <= first && i > last && (first - i) % -step == 0);
                if (!remove) result->append_row(*self->data, i);
            }
            self->data = std::move(result);
        }
        Py_RETURN_NONE;
    }));
    return result ? 0 : -1;
}

PyObject *iterator_new(Storage *self, size_t first) {
    auto *iterator = PyObject_New(Iterator, &IteratorType);
    if (!iterator) return nullptr;
    new (&iterator->data) SharedData(self->data);
    iterator->index = first;
    return reinterpret_cast<PyObject *>(iterator);
}

PyObject *storage_iter(Storage *self) { return iterator_new(self, 0); }
PyObject *storage_iter_from(Storage *self, PyObject *first) {
    Py_ssize_t i = PyNumber_AsSsize_t(first, PyExc_IndexError);
    if (i == -1 && PyErr_Occurred()) return nullptr;
    if (i < 0) i = std::max<Py_ssize_t>(0, storage_length(self) + i);
    return iterator_new(self, i);
}
PyObject *iterator_next(Iterator *self) {
    if (self->index >= self->data->size()) return nullptr;
    PyObject *row = self->data->row(self->index);
    if (row) ++self->index;
    return row;
}
void iterator_dealloc(Iterator *self) { self->data.~SharedData(); PyObject_Del(self); }

PyObject *storage_concat(PyObject *left, PyObject *right) {
    if (!PyObject_TypeCheck(left, &StorageType) || !PyObject_TypeCheck(right, &StorageType)) Py_RETURN_NOTIMPLEMENTED;
    return checked([&]() -> PyObject * {
        Ref result(wrap(&StorageType, reinterpret_cast<Storage *>(left)->data));
        if (!result || extend(reinterpret_cast<Storage *>(result.get()), right)) return nullptr;
        return result.release();
    });
}

PyObject *storage_with_literal(Storage *self, PyObject *raw_gate) {
    return checked([&]() -> PyObject * {
        Ref gate = literal(raw_gate);
        if (!gate) return nullptr;
        int overflow = 0;
        long number = PyLong_AsLongAndOverflow(gate.get(), &overflow);
        if (PyErr_Occurred()) return nullptr;
        bool wide_gate = overflow || number < -INT32_MAX || number > INT32_MAX;
        SharedData result = empty_data();
        SharedData snapshot = self->data;
        const auto &source = *snapshot;
        for (size_t i = 0; i < source.size(); ++i) {
            if (wide_gate || source.wide.count(i)) {
                Ref row(source.row(i));
                if (!row) return nullptr;
                Py_ssize_t size = PyTuple_GET_SIZE(row.get());
                Ref gated(PyTuple_New(size + 1));
                if (!gated) return nullptr;
                for (Py_ssize_t j = 0; j < size; ++j) PyTuple_SET_ITEM(gated.get(), j, Py_NewRef(PyTuple_GET_ITEM(row.get(), j)));
                PyTuple_SET_ITEM(gated.get(), size, Py_NewRef(gate.get()));
                if (result->append(gated.get())) return nullptr;
            } else {
                result->literals.insert(result->literals.end(), source.literals.begin() + source.ends[i], source.literals.begin() + source.ends[i + 1]);
                result->literals.push_back(static_cast<int32_t>(number));
                result->ends.push_back(result->literals.size());
            }
        }
        return wrap(&StorageType, std::move(result));
    });
}

PyObject *storage_to_lists(Storage *self, PyObject *) {
    return checked([&]() {
        SharedData source = self->data;
        return source->to_lists(source->maximum());
    });
}
PyObject *storage_export(Storage *self, PyObject *) {
    return checked([&]() -> PyObject * {
        SharedData source = self->data;
        int32_t maximum = source->maximum();
        Ref rows(source->to_lists(maximum)), top(source->max_var(maximum));
        if (!rows || !top) return nullptr;
        return PyTuple_Pack(2, rows.get(), top.get());
    });
}
PyObject *storage_max_var(Storage *self, void *) {
    SharedData source = self->data;
    return source->max_var(source->maximum());
}

PyMethodDef methods[] = {
    {"append", reinterpret_cast<PyCFunction>(storage_append), METH_O, nullptr},
    {"extend", reinterpret_cast<PyCFunction>(storage_extend), METH_O, nullptr},
    {"with_literal", reinterpret_cast<PyCFunction>(storage_with_literal), METH_O, nullptr},
    {"iter_from", reinterpret_cast<PyCFunction>(storage_iter_from), METH_O, nullptr},
    {"to_lists", reinterpret_cast<PyCFunction>(storage_to_lists), METH_NOARGS, nullptr},
    {"export", reinterpret_cast<PyCFunction>(storage_export), METH_NOARGS, nullptr},
    {nullptr, nullptr, 0, nullptr}
};
PyGetSetDef getters[] = {
    {const_cast<char *>("max_var"), reinterpret_cast<getter>(storage_max_var), nullptr, nullptr, nullptr},
    {nullptr, nullptr, nullptr, nullptr, nullptr}
};
PyMappingMethods mapping = {reinterpret_cast<lenfunc>(storage_length), reinterpret_cast<binaryfunc>(storage_get), reinterpret_cast<objobjargproc>(storage_delete)};
PyNumberMethods numbers = {};
PyModuleDef module = {PyModuleDef_HEAD_INIT, "_clauses", nullptr, -1, nullptr};

PyObject *api_create() { return checked([]() { return wrap(&StorageType, empty_data()); }); }
int api_append(PyObject *object, const int32_t *values, size_t count) {
    Ref result(checked([&]() -> PyObject * {
        if (!PyObject_TypeCheck(object, &StorageType)) {
            PyErr_SetString(PyExc_TypeError, "Expected internal clause storage.");
            return nullptr;
        }
        try { writable(reinterpret_cast<Storage *>(object)).PackedClauses::append(values, count); }
        catch (const std::invalid_argument &error) { PyErr_SetString(PyExc_ValueError, error.what()); return nullptr; }
        Py_RETURN_NONE;
    }));
    return result ? 0 : -1;
}
PyObject *api_adopt(PackedClauses *buffer) {
    return checked([&]() {
        auto data = std::allocate_shared<Data>(Allocator<Data>(python_memory), std::move(*buffer));
        return wrap(&StorageType, std::move(data));
    });
}
const hermax::clauses::API api{1, sizeof(PackedClauses), api_create, api_append, api_adopt};

} // namespace

PyMODINIT_FUNC PyInit__clauses() {
    StorageType.tp_name = "hermax.internal._clauses.Storage";
    StorageType.tp_basicsize = sizeof(Storage);
    StorageType.tp_flags = Py_TPFLAGS_DEFAULT;
    StorageType.tp_new = storage_new;
    StorageType.tp_dealloc = reinterpret_cast<destructor>(storage_dealloc);
    StorageType.tp_methods = methods;
    StorageType.tp_getset = getters;
    StorageType.tp_as_mapping = &mapping;
    StorageType.tp_iter = reinterpret_cast<getiterfunc>(storage_iter);
    numbers.nb_add = storage_concat;
    StorageType.tp_as_number = &numbers;
    IteratorType.tp_name = "hermax.internal._clauses.Iterator";
    IteratorType.tp_basicsize = sizeof(Iterator);
    IteratorType.tp_flags = Py_TPFLAGS_DEFAULT;
    IteratorType.tp_dealloc = reinterpret_cast<destructor>(iterator_dealloc);
    IteratorType.tp_iter = PyObject_SelfIter;
    IteratorType.tp_iternext = reinterpret_cast<iternextfunc>(iterator_next);
    if (PyType_Ready(&StorageType) < 0 || PyType_Ready(&IteratorType) < 0) return nullptr;
    Ref result(PyModule_Create(&module));
    if (!result || PyModule_AddObjectRef(result.get(), "Storage", reinterpret_cast<PyObject *>(&StorageType))) return nullptr;
    Ref capsule(PyCapsule_New(const_cast<hermax::clauses::API *>(&api), "hermax.internal._clauses._C_API", nullptr));
    if (!capsule || PyModule_AddObjectRef(result.get(), "_C_API", capsule.get())) return nullptr;
    return result.release();
}
