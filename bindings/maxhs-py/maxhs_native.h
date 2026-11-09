#ifndef HERMAX_MAXHS_NATIVE_H
#define HERMAX_MAXHS_NATIVE_H
#include <optional>
#include <vector>
class MaxHSWrapperNative {
  public:
    MaxHSWrapperNative();
    ~MaxHSWrapperNative();
    MaxHSWrapperNative(const MaxHSWrapperNative &) = delete;
    MaxHSWrapperNative &operator=(const MaxHSWrapperNative &) = delete;
    int newVar();
    void setNInputVars(int n);
    void addClause(const std::vector<int> &clause, std::optional<long long> weight);
    bool solve();
    int status() const;
    long long cost();
    std::vector<int> model();

  private:
    struct Impl;
    Impl *impl_;
};
#endif
