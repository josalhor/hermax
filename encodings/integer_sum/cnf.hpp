#pragma once

#include <utility>
#include <vector>

namespace integer_sum {
struct Cnf {
    std::vector<std::vector<int>> clauses;
    void add(std::vector<int> clause) { clauses.push_back(std::move(clause)); }
};
}
