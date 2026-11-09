#pragma once
#include <cstdint>
#include <memory>
#include <vector>
namespace spb_native {
class Solver {
  public:
    Solver();
    ~Solver();
    int new_var();
    void set_n_input_vars(unsigned int);
    void add_clause(const std::vector<int> &, bool, long long);
    bool solve(const std::vector<int> &, bool);
    int get_status() const;
    uint64_t get_cost();
    bool get_value(int) const;
    std::vector<int> get_model() const;

  private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};
} // namespace spb_native
