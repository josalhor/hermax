#pragma once

#include <signal.h>

#include <bit>
#include <cassert>
#include <cctype>
#include <chrono>
#include <concepts>
#include <cstdint>
#include <functional>
#include <limits>
#include <span>
#include <string_view>
#include <unordered_map>

namespace Aperture {

enum class Predicate : int8_t { LT, LEQ, EQ, GEQ, GT };

enum class SolverMode : int8_t { ACNF, WCNF };

namespace SolverModes {
inline constexpr std::string_view ACNF = "acnf";
inline constexpr std::string_view WCNF = "wcnf";
}  // namespace SolverModes

const std::unordered_map<std::string_view, SolverMode> kSolverModeMap = {
    {SolverModes::ACNF, SolverMode::ACNF},
    {SolverModes::WCNF, SolverMode::WCNF},
};

enum class ProblemType : int8_t { SAT, MAXSAT, WEIGHTED_MAXSAT, BLACKBOX, OBV };

enum class SolverType : int8_t {
  TOPOR,
  CADICAL,
  GLUCOSE,
  KISSAT,
};

enum class EncoderType : int8_t { TOTALIZER, ADDER };

enum class MBExitReason : int8_t { SIZE, ITERATIONS };

namespace SolverTypes {
inline constexpr std::string_view TOPOR = "topor";
inline constexpr std::string_view CADICAL = "cadical";
inline constexpr std::string_view GLUCOSE = "glucose";
inline constexpr std::string_view KISSAT = "kissat";
}  // namespace SolverTypes

const std::unordered_map<std::string_view, SolverType> kSolverTypeMap = {
    {SolverTypes::TOPOR, SolverType::TOPOR},
    {SolverTypes::CADICAL, SolverType::CADICAL},
    {SolverTypes::GLUCOSE, SolverType::GLUCOSE},
    {SolverTypes::KISSAT, SolverType::KISSAT},
};

enum class LocalSearchSolverType : int8_t { NUWLS = 1, DEEPDIST = 2, BAND = 3 };

namespace LocalSearchSolverTypes {
inline constexpr std::string_view NUWLS = "nuwls";
inline constexpr std::string_view DEEPDIST = "deepdist";
inline constexpr std::string_view BAND = "band";
}  // namespace LocalSearchSolverTypes

const std::unordered_map<std::string_view, LocalSearchSolverType>
    kLocalSearchSolverTypeMap = {
        {LocalSearchSolverTypes::NUWLS, LocalSearchSolverType::NUWLS},
        {LocalSearchSolverTypes::DEEPDIST, LocalSearchSolverType::DEEPDIST},
        {LocalSearchSolverTypes::BAND, LocalSearchSolverType::BAND},
};

inline static std::string_view SolverTypeToName(SolverType type) {
  switch (type) {
    case SolverType::TOPOR:
      return "Topor";
    case SolverType::CADICAL:
      return "CaDiCaL";
    case SolverType::GLUCOSE:
      return "Glucose";
    case SolverType::KISSAT:
      return "Kissat";
    default:
      return "Unknown";
  }
}

enum class SolverStatus : int8_t {
  UNSAT,
  SAT,
  ERROR,
  GLOBAL_CONTRADICTION,
  UNKNOWN
};

enum class TLitValue : int8_t { FALSE, TRUE, DONT_CARE, ERROR };

inline TLitValue operator!(TLitValue val) noexcept {
  switch (val) {
    case TLitValue::FALSE:
      return TLitValue::TRUE;
    case TLitValue::TRUE:
      return TLitValue::FALSE;
    default:
      return val;
  }
}

// A helper struct that calls a given function when going out of scope.
struct CallWhenLeavingScope {
  explicit CallWhenLeavingScope(std::function<void()> func)
      : func_(func), enabled_(true) {}
  ~CallWhenLeavingScope() {
    if (func_ && enabled_) func_();
  }

  void Enable() { enabled_ = true; }
  void Disable() { enabled_ = false; }

 private:
  std::function<void()> func_;
  bool enabled_;
};

// Blocks a given signal until the end of the scope.
struct SigScopeBlocker {
  SigScopeBlocker(int signal_to_block) {
    sigemptyset(&new_mask_);
    sigaddset(&new_mask_, signal_to_block);
    sigprocmask(SIG_BLOCK, &new_mask_, &old_mask_);
  }

  ~SigScopeBlocker() { sigprocmask(SIG_SETMASK, &old_mask_, nullptr); }

 private:
  sigset_t old_mask_, new_mask_;
};

using Clock = std::chrono::steady_clock;

// A literal is valid if it is signed and a power of two.
template <typename T>
concept ValidLiteral =
    std::signed_integral<T> && std::has_single_bit(sizeof(T));

// A weight is valid if it is unsigned and a power of two.
template <typename T>
concept ValidWeight =
    std::unsigned_integral<T> && std::has_single_bit(sizeof(T));

template <ValidLiteral TLit, ValidWeight TWeight>
using WLits = std::span<const std::pair<TWeight, TLit>>;

template <ValidLiteral TLit>
using Lits = std::span<const TLit>;

// A helper function to get the absolute value of a literal.
template <ValidLiteral TLit>
inline TLit lit_abs(TLit lit) noexcept {
  return (lit < 0) ? -lit : lit;
};
};  // namespace Aperture
