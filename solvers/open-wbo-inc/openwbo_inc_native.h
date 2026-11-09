#ifndef HERMAX_OPENWBO_INC_NATIVE_H
#define HERMAX_OPENWBO_INC_NATIVE_H
#include <cstdint>
#include <vector>
class OpenWBOIncNative {
  public:
    OpenWBOIncNative();
    ~OpenWBOIncNative();
    OpenWBOIncNative(const OpenWBOIncNative &) = delete;
    OpenWBOIncNative &operator=(const OpenWBOIncNative &) = delete;
    int new_var();
    void add_clause(const std::vector<int> &clause, bool soft, long long weight);
    bool solve();
    uint64_t cost() const;
    bool value(int var) const;

  private:
    struct Impl;
    Impl *impl_;
};
#endif
