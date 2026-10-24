#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <climits>
#include <unordered_set>

#include "order_sum.hpp"
#include "pb_budget.hpp"
#include "pb2cnf.h"

namespace py = pybind11;
using integer_sum::Chains;

static std::int64_t integer(py::handle value, const char* label) {
    if (!PyLong_Check(value.ptr()) || PyBool_Check(value.ptr()))
        throw py::type_error(std::string(label) + " must be an integer");
    auto out = PyLong_AsLongLong(value.ptr());
    if (PyErr_Occurred()) throw py::error_already_set();
    return out;
}

static int small_integer(py::handle value, const char* label) {
    const auto out = integer(value, label);
    if (out < INT_MIN || out > INT_MAX) throw std::overflow_error(label);
    return static_cast<int>(out);
}

static int literal(py::handle value) {
    const int out = small_integer(value, "literal");
    if (!out || out == INT_MIN) throw py::value_error("invalid literal");
    return out;
}

static Chains read_chains(py::iterable groups, int& top) {
    Chains result;
    std::unordered_set<int> seen;
    std::int64_t total = 0;
    for (auto group : groups) {
        std::vector<int> row;
        for (auto item : py::reinterpret_borrow<py::iterable>(group)) {
            const int lit = literal(item);
            if (!seen.insert(std::abs(lit)).second)
                throw py::value_error("threshold chains must be disjoint");
            top = std::max(top, std::abs(lit));
            row.push_back(lit);
            if (++total > INT_MAX) throw std::overflow_error("order sum is too large");
        }
        if (!row.empty()) result.push_back(std::move(row));
    }
    return result;
}

static py::tuple encode_order_sum(py::iterable groups, py::object bound_value,
                                 py::object top_value, py::object mode_value,
                                 py::object modulus_value) {
    int top = small_integer(top_value, "top_id");
    const int bound = small_integer(bound_value, "bound");
    const int mode = small_integer(mode_value, "mode");
    const int modulus = small_integer(modulus_value, "modulus");
    if (top < 0 || mode < 0 || mode > 1 || modulus < 0 || modulus == 1)
        throw py::value_error("invalid order-sum configuration");
    auto groups_read = read_chains(groups, top);
    integer_sum::Cnf cnf;
    integer_sum::encode(groups_read, bound, mode, modulus, top, cnf);
    if (PyErr_CheckSignals() < 0) throw py::error_already_set();
    return py::make_tuple(std::move(cnf.clauses), top);
}

static py::dict assess_order_sum(py::iterable values, py::object bound_value) {
    const int bound = small_integer(bound_value, "bound");
    std::vector<std::size_t> widths;
    std::int64_t total = 0;
    for (auto value : values) {
        const int w = small_integer(value, "width");
        if (w < 0) throw py::value_error("width must be nonnegative");
        if ((total += w) > INT_MAX) throw std::overflow_error("order sum is too large");
        if (w) widths.push_back(w);
    }
    const auto plan = integer_sum::assess(widths, bound);
    py::dict result;
    result["leaf_variables"] = plan.leaf.variables;
    result["leaf_clauses"] = plan.leaf.clauses;
    result["whole_variables"] = plan.whole.variables;
    result["whole_clauses"] = plan.whole.clauses;
    result["modulus"] = plan.modulus;
    return result;
}

static py::tuple encode_pb(py::iterable pairs, int comparator, std::int64_t bound,
                           int top, int encoder, py::iterable conditions,
                           std::int64_t state_limit, std::int64_t clause_limit) {
    if (state_limit < 0 || clause_limit < 0 || top < 0)
        throw py::value_error("limits and top_id must be nonnegative");
    if (comparator != PBLib::LEQ && comparator != PBLib::GEQ && comparator != PBLib::BOTH)
        throw py::value_error("invalid comparator");
    if (encoder < 0 || encoder > 7 || encoder == 6) throw py::value_error("invalid encoder");
    std::vector<PBLib::WeightedLit> terms;
    std::vector<std::int64_t> weights;
    std::unordered_set<int> seen;
    for (auto pair : pairs) {
        auto entry = py::reinterpret_borrow<py::sequence>(pair);
        if (py::len(entry) != 2) throw py::value_error("expected a literal and weight");
        const int lit = literal(entry[0]);
        const auto weight = integer(entry[1], "weight");
        if (weight <= 0 || !seen.insert(std::abs(lit)).second)
            throw py::value_error("expected distinct literals with positive weights");
        terms.emplace_back(lit, weight);
        weights.push_back(weight);
        top = std::max(top, std::abs(lit));
    }
    integer_sum::total_weight(weights);
    if (state_limit) integer_sum::count_states(weights, bound, static_cast<PBLib::Comparator>(comparator), state_limit);
    PBLib::PBConstraint constraint(terms, static_cast<PBLib::Comparator>(comparator), bound);
    std::vector<std::int32_t> guards;
    for (auto item : conditions) {
        const int lit = literal(item);
        guards.push_back(lit);
        top = std::max(top, std::abs(lit));
    }
    constraint.addConditionals(guards);
    if (top == INT_MAX) throw std::overflow_error("variable IDs exhausted");
    PBConfig config = std::make_shared<PBConfigClass>();
    config->pb_encoder = static_cast<PB_ENCODER::PB2CNF_PB_Encoder>(encoder == 7 ? 5 : encoder);
    if (encoder == 7) {
        config->use_watch_dog_encoding_in_binary_merger = true;
        config->use_gac_binary_merge = true;
    }
    integer_sum::ClauseSink sink(config, clause_limit);
    AuxVarManager variables(top + 1);
    PB2CNF compiler(config);
    compiler.encode(constraint, sink, variables);
    if (PyErr_CheckSignals() < 0) throw py::error_already_set();
    return py::make_tuple(std::move(sink.clauses), std::max(top, variables.getBiggestReturnedAuxVar()));
}

PYBIND11_MODULE(_integer_sum_native, module) {
    py::register_exception<integer_sum::BudgetExceeded>(module, "EncodingBudgetExceeded", PyExc_RuntimeError);
    module.def("encode_order_sum", &encode_order_sum, py::arg("chains"), py::arg("bound"),
               py::arg("top_id"), py::arg("mode") = 0, py::arg("modulus") = 0);
    module.def("assess_order_sum", &assess_order_sum);
    module.def("count_states", [](std::vector<std::int64_t> weights, std::int64_t bound, int comparator, std::int64_t limit) {
        if (limit < 0 || (comparator != PBLib::LEQ && comparator != PBLib::GEQ && comparator != PBLib::BOTH))
            throw py::value_error("invalid state counter configuration");
        return integer_sum::count_states(std::move(weights), bound, static_cast<PBLib::Comparator>(comparator), limit);
    }, py::arg("weights"), py::arg("bound"), py::arg("comparator"), py::arg("limit") = 20'000);
    module.def("encode_pb", &encode_pb, py::arg("wlits"), py::arg("comparator"),
               py::arg("bound"), py::arg("top_id"), py::arg("pb_encoder"),
               py::arg("conditionals"), py::arg("state_limit") = 0, py::arg("clause_limit") = 0);
    module.attr("LEQ") = static_cast<int>(PBLib::LEQ);
    module.attr("GEQ") = static_cast<int>(PBLib::GEQ);
    module.attr("BOTH") = static_cast<int>(PBLib::BOTH);
    module.attr("PB_BEST") = 0;
    module.attr("PB_BDD") = 1;
    module.attr("PB_SWC") = 2;
    module.attr("PB_SORTINGNETWORKS") = 3;
    module.attr("PB_ADDER") = 4;
    module.attr("PB_BINARY_MERGE") = 5;
    module.attr("PB_LPW") = 7;
}
