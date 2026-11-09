#pragma once
#include <cstdint>
#include <memory>
#include <vector>
namespace wmaxcdcl_native {
class Solver {
  public:
    Solver();
    ~Solver();
    int new_var(bool decision_var);
    bool add_clause(const std::vector<int> &, bool, long long);
    void set_n_input_vars(unsigned int);
    void prepare();
    bool solve(const std::vector<int> &, bool);
    long long get_cost() const;
    bool get_value(int) const;
    std::vector<int> get_model() const;

  private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};
} // namespace wmaxcdcl_native
