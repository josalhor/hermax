#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
#include <optional>
#include <functional>
#include <cmath>
#include "../../../solvers/incremental-maxhs/src/ipamir/ipamir.h"

namespace py = pybind11;

// Helper function for the termination callback
int terminate_callback_wrapper(void* state) {
    if (!state) return 0;
    auto* callback = static_cast<std::function<int()>*>(state);
    try {
        return (*callback)();
    } catch (py::error_already_set& e) {
        e.restore(); // Propagate Python exception
        return 1; // Indicate termination due to error
    }
}

class IMaxHS {
public:
    void* solver;
    std::function<int()> terminate_callback;
    int num_vars;

    IMaxHS() : solver(ipamir_init()), num_vars(0) {
        if (!solver) {
            throw std::runtime_error("Failed to initialize IMaxHS solver.");
        }
    }

    ~IMaxHS() {
        if (solver) {
            ipamir_release(solver);
            solver = nullptr;
        }
    }

    IMaxHS(const IMaxHS&) = delete;
    IMaxHS& operator=(const IMaxHS&) = delete;

    int newVar() {
        return ++num_vars;
    }

    void addClause(const std::vector<int>& clause, std::optional<long long> weight_opt) {
        for (int lit : clause) {
            int var = std::abs(lit);
            if (var > num_vars) {
                num_vars = var;
            }
        }

        if (!weight_opt.has_value()) { // Hard clause
            for (int lit : clause) {
                ipamir_add_hard(solver, lit);
            }
            ipamir_add_hard(solver, 0);
        } else { // Soft clause
            long long weight = weight_opt.value();
            if (clause.size() == 1) {
                // ipamir_add_soft_lit(L, w) means cost w if L is true.
                // DIMACS soft clause (C) w means cost w if C is false.
                // For unit clause (l), it means cost w if l is false, i.e., -l is true.
                ipamir_add_soft_lit(solver, -clause[0], static_cast<uint64_t>(weight));
            } else {
                int aux_var = newVar();
                for (int lit : clause) {
                    ipamir_add_hard(solver, lit);
                }
                ipamir_add_hard(solver, aux_var);
                ipamir_add_hard(solver, 0);
                ipamir_add_soft_lit(solver, aux_var, static_cast<uint64_t>(weight));
            }
        }
    }

    void assume(const std::vector<int>& assumptions) {
        for (int lit : assumptions) {
            ipamir_assume(solver, lit);
        }
    }

    int solve() {
        return ipamir_solve(solver);
    }

    uint64_t getCost() {
        return ipamir_val_obj(solver);
    }

    py::object getValue(int lit) {
        int val = ipamir_val_lit(solver, lit);
        if (val == lit) {
            return py::cast(true);
        } else if (val == -lit) {
            return py::cast(false);
        } else {
            return py::none();
        }
    }

    void set_terminate(std::optional<std::function<int()>> callback) {
        if (callback) {
            terminate_callback = callback.value();
            ipamir_set_terminate(solver, &terminate_callback, terminate_callback_wrapper);
        } else {
            ipamir_set_terminate(solver, nullptr, nullptr);
        }
    }

    const char* signature() const {
        return ipamir_signature();
    }
};

PYBIND11_MODULE(imaxhs_py, m) {
    m.doc() = "pybind11 plugin for IMaxHS";

    py::class_<IMaxHS>(m, "IMaxHS")
        .def(py::init<>())
        .def("newVar", &IMaxHS::newVar, "Generates a new variable ID.")
        .def("addClause", &IMaxHS::addClause,
             py::arg("clause"), py::arg("weight") = std::nullopt,
             "Adds a clause. If weight is None, it's a hard clause.")
        .def("assume", &IMaxHS::assume, "Add assumptions for the next solve call.")
        .def("solve", &IMaxHS::solve, "Solve the instance under the current assumptions.")
        .def("getCost", &IMaxHS::getCost, "Get the cost of the optimal solution.")
        .def("getValue", &IMaxHS::getValue, "Get the truth value of a literal in the model.")
        .def("set_terminate", &IMaxHS::set_terminate, "Set a termination callback.")
        .def("signature", &IMaxHS::signature, "Get the solver signature string.");
}
