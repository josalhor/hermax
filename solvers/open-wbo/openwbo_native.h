#pragma once
#include <cstdint>
#include <memory>
#include <vector>
namespace openwbo_native {
class Solver {
  public:
    enum class Kind { OLL, PartMSU3, Auto };
    explicit Solver(Kind);
    ~Solver();
    int new_var();
    void add_clause(const std::vector<int> &, bool, long long);
    bool solve(const std::vector<int> &, bool);
    uint64_t get_cost() const;
    bool get_value(int) const;

  private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};
} // namespace openwbo_native
