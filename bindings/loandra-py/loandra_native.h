#pragma once
#include <cstdint>
#include <memory>
#include <vector>
namespace loandra_native {
class Solver {
  public:
    Solver();
    ~Solver();
    int new_var();
    void add_clause(const std::vector<int> &, bool, long long);
    bool solve();
    uint64_t get_cost();
    bool get_value(int);
    std::vector<int> get_model() const;

  private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};
} // namespace loandra_native
