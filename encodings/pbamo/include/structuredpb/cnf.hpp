#ifndef STRUCTUREDPB_CNF_HPP
#define STRUCTUREDPB_CNF_HPP

#include <algorithm>
#include <cstdlib>
#include <initializer_list>
#include <stdexcept>
#include <vector>
#include <limits>

namespace structuredpb {

using Clause = std::vector<int>;

struct CnfFormula {
    int num_vars = 0;
    std::vector<Clause> clauses;

    void add_clause(Clause clause) {
        for (int lit : clause) {
            if (lit == 0) {
                throw std::invalid_argument("structuredpb: clause contains literal 0");
            }
            num_vars = std::max(num_vars, std::abs(lit));
        }
        clauses.push_back(std::move(clause));
    }

    void add_clause(std::initializer_list<int> clause) {
        add_clause(Clause(clause));
    }
};

class VariableManager {
public:
    explicit VariableManager(int top_id = 0) : max_var_(top_id) {
        if (top_id < 0) {
            throw std::invalid_argument("structuredpb: top_id must be non-negative");
        }
    }

    int new_var() {
        if (max_var_ == std::numeric_limits<int>::max()) {
            throw std::overflow_error("structuredpb: variable ID range exhausted");
        }
        return ++max_var_;
    }

    int max_var() const { return max_var_; }

private:
    int max_var_;
};

}  // namespace structuredpb

#endif
