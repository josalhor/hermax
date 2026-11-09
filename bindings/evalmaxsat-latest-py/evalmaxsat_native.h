#pragma once

#include <memory>
#include <optional>
#include <vector>

namespace evalmaxsat_native {
class Solver {
  public:
    Solver();
    ~Solver();
    int new_var(bool decision_var);
    int add_clause(const std::vector<int> &clause, std::optional<long long> weight);
    bool solve();
    long long get_cost();
    bool get_value(int lit);
    std::vector<int> get_model();
    void set_n_input_vars(unsigned int n);

  private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};
} // namespace evalmaxsat_native
