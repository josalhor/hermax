#ifndef HERMAX_APERTURE_NATIVE_H
#define HERMAX_APERTURE_NATIVE_H
#include <cstdint>
#include <vector>
class ApertureBackend {
  public:
    ApertureBackend();
    ~ApertureBackend();
    ApertureBackend(const ApertureBackend &) = delete;
    ApertureBackend &operator=(const ApertureBackend &) = delete;
    int new_var();
    void add_clause(const std::vector<int32_t> &clause);
    void set_soft(int32_t lit, uint64_t weight);
    void assume(int32_t lit);
    int solve();
    uint64_t objective_value() const;
    int32_t value(int32_t lit) const;
    const char *signature() const;

  private:
    struct Impl;
    Impl *impl_;
};
#endif
