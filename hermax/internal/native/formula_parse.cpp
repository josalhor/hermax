#define PY_SSIZE_T_CLEAN
#include "formula_parse.hpp"

#include <algorithm>
#include <charconv>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace hermax::formula {
namespace {

struct Decref {
    void operator()(PyObject *value) const { Py_XDECREF(value); }
};
using Ref = std::unique_ptr<PyObject, Decref>;

template <typename Function> PyObject *checked(Function function) noexcept {
    try { return function(); }
    catch (const std::bad_alloc &) { return PyErr_NoMemory(); }
    catch (const std::length_error &) { return PyErr_NoMemory(); }
}

Ref dimacs_integer(const std::string &token) {
    size_t first = (!token.empty() && (token[0] == '-' || token[0] == '+')) ? 1 : 0;
    if (first == token.size() || token.empty() ||
        token.find_first_not_of("0123456789", first) != std::string::npos) {
        PyErr_SetString(PyExc_ValueError, "Expected an integer in DIMACS formula.");
        return {};
    }
    return Ref(PyLong_FromString(token.c_str(), nullptr, 10));
}

} // namespace

PyObject *parse(PyObject *args, const ClauseBuilder &storage) {
    const char *text;
    Py_ssize_t length;
    int weighted, plus;
    if (!PyArg_ParseTuple(args, "s#pp", &text, &length, &weighted, &plus)) return nullptr;
    return checked([&]() -> PyObject * {
        Ref hard(storage.create()), soft(storage.create());
        Ref weights(PyList_New(0)), constraints(PyList_New(0)), comments(PyList_New(0));
        Ref nv(PyLong_FromLong(0)), top, declared_count, zero(PyLong_FromLong(0));
        size_t records = 0;
        if (!hard || !soft || !weights || !constraints || !comments || !nv || !zero) return nullptr;
        std::istringstream lines(std::string(text, length));
        std::string line;
        std::vector<std::string> pending;
        bool header = false, data = false;
        auto error = [](const char *message) -> PyObject * {
            PyErr_SetString(PyExc_ValueError, message); return nullptr;
        };
        auto add_record = [&](const std::vector<std::string> &tokens) -> bool {
            size_t start = weighted ? 1 : 0;
            if (tokens.size() <= start) { error("Missing formula clause."); return false; }
            Ref weight;
            bool is_hard = !weighted || tokens[0] == "h";
            if (weighted && !is_hard) {
                weight = dimacs_integer(tokens[0]);
                if (!weight) return false;
                int positive = PyObject_RichCompareBool(weight.get(), zero.get(), Py_GT);
                if (positive <= 0) { if (!PyErr_Occurred()) error("Soft weights must be positive integers."); return false; }
                if (top) {
                    int cmp = PyObject_RichCompareBool(weight.get(), top.get(), Py_GE);
                    if (cmp < 0) return false;
                    is_hard = cmp;
                }
            }
            size_t op = tokens.size();
            for (size_t i = start; i < tokens.size(); ++i)
                if (tokens[i] == "<=" || tokens[i] == ">=") { op = i; break; }
            Ref literals(PyList_New(0));
            if (!literals) return false;
            if (op < tokens.size()) {
                if (!plus) { error("Native constraints require a Plus formula."); return false; }
                if (!is_hard) { error("Native constraints must be hard."); return false; }
                if (op + 2 != tokens.size()) { error("Malformed native constraint."); return false; }
                bool has_weights = tokens[start] == "w";
                Ref coefficients(PyList_New(0)), total(PyLong_FromLong(0));
                if (!coefficients || !total) return false;
                for (size_t i = start + has_weights; i < op; ++i) {
                    Ref coefficient, literal;
                    if (has_weights) {
                        size_t split = tokens[i].find('*');
                        if (split == std::string::npos) { error("Expected weight*literal."); return false; }
                        coefficient = dimacs_integer(tokens[i].substr(0, split));
                        literal = dimacs_integer(tokens[i].substr(split + 1));
                    } else {
                        coefficient = Ref(PyLong_FromLong(1));
                        literal = dimacs_integer(tokens[i]);
                    }
                    if (!coefficient || !literal) return false;
                    int negative = PyObject_RichCompareBool(coefficient.get(), zero.get(), Py_LT);
                    if (negative != 0) { if (negative > 0) error("Constraint weights cannot be negative."); return false; }
                    total = Ref(PyNumber_Add(total.get(), coefficient.get()));
                    if (!total || PyList_Append(coefficients.get(), coefficient.get()) < 0) return false;
                    if (tokens[op] == ">=") literal = Ref(PyNumber_Negative(literal.get()));
                    if (!literal || PyList_Append(literals.get(), literal.get()) < 0) return false;
                }
                Ref bound = dimacs_integer(tokens.back());
                if (!bound) return false;
                if (tokens[op] == ">=") bound = Ref(PyNumber_Subtract(total.get(), bound.get()));
                // Storage validates literal zero, index semantics and integer width.
                for (Py_ssize_t i = 0; i < PyList_GET_SIZE(literals.get()); ++i) {
                    if (!PyObject_IsTrue(PyList_GET_ITEM(literals.get(), i))) {
                        error("DIMACS literal zero is invalid.");
                        return false;
                    }
                }
                Ref constraint(PyList_New(has_weights ? 3 : 2));
                if (!constraint || !bound) return false;
                PyList_SET_ITEM(constraint.get(), 0, literals.release());
                PyList_SET_ITEM(constraint.get(), 1, bound.release());
                if (has_weights) PyList_SET_ITEM(constraint.get(), 2, coefficients.release());
                return PyList_Append(constraints.get(), constraint.get()) == 0;
            }
            if (tokens.back() != "0") { error("Unterminated DIMACS clause."); return false; }
            // Common solver-sized clauses go directly from text to packed
            // int32 storage, without allocating a Python integer per literal.
            std::vector<int32_t> narrow;
            narrow.reserve(tokens.size() - start - 1);
            bool all_narrow = true;
            for (size_t i = start; i + 1 < tokens.size(); ++i) {
                const auto& token = tokens[i];
                const char* begin = token.data() + (!token.empty() && token[0] == '+');
                const char* end = token.data() + token.size();
                int32_t value;
                const auto parsed = std::from_chars(begin, end, value);
                if (parsed.ec != std::errc() || parsed.ptr != end || value == INT32_MIN) {
                    all_narrow = false;
                    break;
                }
                if (!value) { error("DIMACS literal zero is invalid."); return false; }
                narrow.push_back(value);
            }
            if (all_narrow) {
                if (storage.append_narrow((is_hard ? hard : soft).get(),
                                          narrow.data(), narrow.size()) < 0) return false;
                return is_hard || PyList_Append(weights.get(), weight.get()) == 0;
            }
            for (size_t i = start; i + 1 < tokens.size(); ++i) {
                Ref literal = dimacs_integer(tokens[i]);
                if (!literal || PyList_Append(literals.get(), literal.get()) < 0) return false;
            }
            if (storage.append((is_hard ? hard : soft).get(), literals.get()) < 0) return false;
            return is_hard || PyList_Append(weights.get(), weight.get()) == 0;
        };
        while (std::getline(lines, line)) {
            std::istringstream fields(line);
            std::vector<std::string> tokens;
            std::string token;
            while (fields >> token) tokens.push_back(token);
            if (tokens.empty()) continue;
            if (tokens[0] == "c") {
                Ref comment(PyUnicode_FromString(line.substr(line.find_first_not_of(" \t\r")).c_str()));
                if (!comment || PyList_Append(comments.get(), comment.get()) < 0) return nullptr;
                continue;
            }
            if (tokens[0] == "p") {
                if (header || data || tokens.size() < 4 || tokens.size() > (weighted ? 5U : 4U))
                    return error("Malformed or misplaced DIMACS header.");
                const std::string expected = weighted ? "wcnf" : "cnf";
                if (tokens[1] != expected && (!plus || tokens[1] != expected + "+"))
                    return error("Unexpected DIMACS formula kind.");
                nv = dimacs_integer(tokens[2]);
                declared_count = dimacs_integer(tokens[3]);
                if (!nv || !declared_count) return nullptr;
                if (PyObject_RichCompareBool(nv.get(), zero.get(), Py_LT) != 0 ||
                    PyObject_RichCompareBool(declared_count.get(), zero.get(), Py_LT) != 0)
                    return error("Negative DIMACS header count.");
                if (tokens.size() == 5) {
                    top = dimacs_integer(tokens[4]);
                    if (!top) return nullptr;
                    if (PyObject_RichCompareBool(top.get(), zero.get(), Py_GT) != 1)
                        return error("Hard weight must be positive.");
                }
                header = true;
                continue;
            }
            data = true;
            bool constraint = std::find(tokens.begin(), tokens.end(), "<=") != tokens.end() ||
                              std::find(tokens.begin(), tokens.end(), ">=") != tokens.end();
            if (constraint) {
                if (!pending.empty()) return error("Constraint inside an unfinished clause.");
                if (!add_record(tokens)) return nullptr;
                ++records;
            } else {
                for (const auto &item : tokens) {
                    pending.push_back(item);
                    if (item == "0") {
                        if (!add_record(pending)) return nullptr;
                        ++records;
                        pending.clear();
                    }
                }
            }
        }
        if (!pending.empty()) return error("Unterminated DIMACS clause.");
        if (header) {
            Ref actual_count(PyLong_FromSize_t(records));
            if (!actual_count) return nullptr;
            if (PyObject_RichCompareBool(actual_count.get(), declared_count.get(), Py_EQ) != 1)
                return error("DIMACS clause count does not match header.");
            Ref hmax(storage.max_var(hard.get()));
            Ref smax(storage.max_var(soft.get()));
            if (!hmax || !smax) return nullptr;
            if (PyObject_RichCompareBool(hmax.get(), nv.get(), Py_GT) != 0 ||
                PyObject_RichCompareBool(smax.get(), nv.get(), Py_GT) != 0)
                return error("Literal exceeds declared variable count.");
            for (Py_ssize_t i = 0; i < PyList_GET_SIZE(constraints.get()); ++i) {
                PyObject *lits = PyList_GET_ITEM(PyList_GET_ITEM(constraints.get(), i), 0);
                for (Py_ssize_t j = 0; j < PyList_GET_SIZE(lits); ++j) {
                    Ref absolute(PyNumber_Absolute(PyList_GET_ITEM(lits, j)));
                    if (!absolute) return nullptr;
                    if (PyObject_RichCompareBool(absolute.get(), nv.get(), Py_GT) != 0)
                        return error("Literal exceeds declared variable count.");
                }
            }
        }
        return PyTuple_Pack(7, hard.get(), soft.get(), weights.get(), constraints.get(),
                            nv.get(), top ? top.get() : Py_None, comments.get());
    });
}

} // namespace hermax::formula
