#pragma once

#include <utility>
#include <vector>
#include "native/packed_clauses.hpp"

namespace integer_sum {
struct Cnf {
    hermax::clauses::PackedClauses clauses;
    explicit Cnf(hermax::clauses::Memory memory = {}) : clauses(memory) {}
    void add(const std::vector<int>& clause) { clauses.push_back(clause); }
};
}
