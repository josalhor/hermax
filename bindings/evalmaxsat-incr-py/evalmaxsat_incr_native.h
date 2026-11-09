#pragma once
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>
namespace evalmaxsat_incr_native {
class Solver {
  public:
    Solver();
    ~Solver();
    void add_clause(const std::vector<int> &clause, std::optional<long long> weight);
    void add_soft_lit(int lit, uint64_t weight);
    void assume(const std::vector<int> &assumptions);
    int solve();
    uint64_t get_cost();
    int get_value(int lit);
    std::string signature();

  private:
    void *solver_;
};
} // namespace evalmaxsat_incr_native
