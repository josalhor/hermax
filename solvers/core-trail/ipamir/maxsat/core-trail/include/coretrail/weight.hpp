#pragma once

#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <type_traits>
#include <variant>
#include <functional>

namespace coretrail {

// Numeric objective value that retains exact int64 arithmetic for integer-only
// operations and uses IEEE double arithmetic whenever either operand is real.
class Weight {
public:
    Weight() : value_(std::int64_t{0}) {}
    Weight(std::int64_t v) : value_(v) {}
    Weight(int v) : value_(static_cast<std::int64_t>(v)) {}
    Weight(double v) : value_(v) { validate_double(v); }

    bool is_integer() const noexcept { return std::holds_alternative<std::int64_t>(value_); }
    std::int64_t as_integer() const { return std::get<std::int64_t>(value_); }
    double as_double() const noexcept {
        return is_integer() ? static_cast<double>(std::get<std::int64_t>(value_)) : std::get<double>(value_);
    }
    bool finite() const noexcept { return is_integer() || std::isfinite(std::get<double>(value_)); }

    Weight operator-() const {
        if (is_integer()) {
            const auto v = as_integer();
            if (v == std::numeric_limits<std::int64_t>::min()) throw std::overflow_error("weight negation overflow");
            return Weight(-v);
        }
        return Weight(-as_double());
    }
    friend Weight operator+(const Weight& a, const Weight& b) {
        if (a.is_integer() && b.is_integer()) return Weight(checked_add(a.as_integer(), b.as_integer()));
        return Weight(a.as_double() + b.as_double());
    }
    friend Weight operator-(const Weight& a, const Weight& b) {
        if (a.is_integer() && b.is_integer()) return Weight(checked_sub(a.as_integer(), b.as_integer()));
        return Weight(a.as_double() - b.as_double());
    }
    Weight& operator+=(const Weight& rhs) { return *this = *this + rhs; }
    Weight& operator-=(const Weight& rhs) { return *this = *this - rhs; }
    friend Weight operator*(const Weight& a, std::int64_t b) {
        if (a.is_integer()) return Weight(checked_mul(a.as_integer(), b));
        return Weight(a.as_double() * static_cast<double>(b));
    }
    friend Weight operator*(std::int64_t a, const Weight& b) { return b * a; }
    friend bool operator==(const Weight& a, const Weight& b) {
        if (a.is_integer() && b.is_integer()) return a.as_integer() == b.as_integer();
        if (a.is_integer() && !b.is_integer()) {
            return equal_integer_double(a.as_integer(), b.as_double());
        }
        if (!a.is_integer() && b.is_integer()) return b == a;
        return a.as_double() == b.as_double();
    }
    friend bool operator!=(const Weight& a, const Weight& b) { return !(a == b); }
    friend bool operator<(const Weight& a, const Weight& b) {
        if (a.is_integer() && b.is_integer()) return a.as_integer() < b.as_integer();
        if (a.is_integer()) return integer_less_double(a.as_integer(), b.as_double());
        if (b.is_integer()) return !integer_less_double(b.as_integer(), a.as_double()) &&
            !equal_integer_double(b.as_integer(), a.as_double());
        return a.as_double() < b.as_double();
    }
    friend bool operator>(const Weight& a, const Weight& b) { return b < a; }
    friend bool operator<=(const Weight& a, const Weight& b) { return !(b < a); }
    friend bool operator>=(const Weight& a, const Weight& b) { return !(a < b); }
    friend bool operator==(const Weight& a, std::int64_t b) { return a == Weight(b); }
    friend bool operator==(std::int64_t a, const Weight& b) { return Weight(a) == b; }
    friend bool operator!=(const Weight& a, std::int64_t b) { return !(a == b); }
    friend bool operator<(const Weight& a, std::int64_t b) { return a < Weight(b); }
    friend bool operator>(const Weight& a, std::int64_t b) { return Weight(b) < a; }
    friend bool operator<=(const Weight& a, std::int64_t b) { return !(a > b); }
    friend bool operator>=(const Weight& a, std::int64_t b) { return !(a < b); }

private:
    std::variant<std::int64_t, double> value_;
    static bool integer_less_double(std::int64_t i, double d) {
        constexpr double i64_min = -9223372036854775808.0;
        constexpr double i64_limit = 9223372036854775808.0;
        if (d >= i64_limit) return true;
        if (d < i64_min) return false;
        const auto truncated = static_cast<std::int64_t>(d);
        if (i != truncated) return i < truncated;
        return d > static_cast<double>(truncated);
    }
    static bool equal_integer_double(std::int64_t i, double d) {
        constexpr double i64_min = -9223372036854775808.0;
        constexpr double i64_limit = 9223372036854775808.0;
        return d >= i64_min && d < i64_limit && std::trunc(d) == d &&
            i == static_cast<std::int64_t>(d);
    }
    static void validate_double(double v) {
        if (!std::isfinite(v)) throw std::invalid_argument("weight must be finite");
    }
    static std::int64_t checked_add(std::int64_t a, std::int64_t b) {
        if ((b > 0 && a > std::numeric_limits<std::int64_t>::max() - b) ||
            (b < 0 && a < std::numeric_limits<std::int64_t>::min() - b))
            throw std::overflow_error("integer weight overflow");
        return a + b;
    }
    static std::int64_t checked_sub(std::int64_t a, std::int64_t b) {
        if ((b < 0 && a > std::numeric_limits<std::int64_t>::max() + b) ||
            (b > 0 && a < std::numeric_limits<std::int64_t>::min() + b))
            throw std::overflow_error("integer weight overflow");
        return a - b;
    }
    static std::int64_t checked_mul(std::int64_t a, std::int64_t b) {
        if (a == 0 || b == 0) return 0;
        if (a == -1 && b == std::numeric_limits<std::int64_t>::min()) throw std::overflow_error("integer weight overflow");
        if (b == -1 && a == std::numeric_limits<std::int64_t>::min()) throw std::overflow_error("integer weight overflow");
        if (a > 0 ? (b > 0 ? a > std::numeric_limits<std::int64_t>::max() / b : b < std::numeric_limits<std::int64_t>::min() / a)
                  : (b > 0 ? a < std::numeric_limits<std::int64_t>::min() / b : a < std::numeric_limits<std::int64_t>::max() / b))
            throw std::overflow_error("integer weight overflow");
        return a * b;
    }
};

inline Weight weight_min(const Weight& a, const Weight& b) { return a < b ? a : b; }
inline Weight weight_max(const Weight& a, const Weight& b) { return a < b ? b : a; }

}  // namespace coretrail

namespace std {
template <> struct hash<coretrail::Weight> {
    size_t operator()(const coretrail::Weight& w) const noexcept {
        if (w.is_integer()) return hash<int64_t>{}(w.as_integer());
        const double d = w.as_double();
        constexpr double i64_min = -9223372036854775808.0;
        constexpr double i64_limit = 9223372036854775808.0;
        if (d >= i64_min && d < i64_limit && std::trunc(d) == d)
            return hash<int64_t>{}(static_cast<int64_t>(d));
        return hash<double>{}(d);
    }
};
}  // namespace std



