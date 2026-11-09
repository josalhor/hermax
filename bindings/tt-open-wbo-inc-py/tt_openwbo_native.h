#ifndef HERMAX_TT_OPENWBO_NATIVE_H
#define HERMAX_TT_OPENWBO_NATIVE_H
#include <cstdint>
#include <vector>
class TTOpenWBOIncNative {
  public:
    TTOpenWBOIncNative();
    ~TTOpenWBOIncNative();
    TTOpenWBOIncNative(const TTOpenWBOIncNative &) = delete;
    TTOpenWBOIncNative &operator=(const TTOpenWBOIncNative &) = delete;
    int new_var();
    void add_clause(const std::vector<int> &, bool, long long);
    bool solve();
    uint64_t cost() const;
    bool value(int) const;

  private:
    struct Impl;
    Impl *impl_;
};
#endif
