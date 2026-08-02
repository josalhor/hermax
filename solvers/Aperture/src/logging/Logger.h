#pragma once

#include "../ATypes.h"

#define FMT_HEADER_ONLY
#include <fmt/color.h>
#include <fmt/core.h>
#include <fmt/ostream.h>
#if defined(__MINGW32__)
#include <process.h>
#else
#include <unistd.h>
#endif

#include <fstream>
#include <optional>
#include <span>
#include <sstream>

namespace Aperture {

enum class VerbosityLevel : int8_t {
  SILENT = 0,
  NORMAL = 1,
  VERBOSE = 2,
  VVERBOSE = 3
};

enum class LogSource : int8_t { SOLVER = 0, EXTERNAL = 1 };

class Logger {
 public:
  static Logger& Instance() { return instance_; }

  // Logs a formatted message with a "c" prefix if the verbosity level allows
  // it.
  template <typename... Args>
  void Log(VerbosityLevel verbosity, LogSource source,
           fmt::format_string<Args...> fmt, Args... args) {
    LogPrefixed(verbosity, source, "c ", fmt, std::forward<Args>(args)...);
  }

  // Logs a formatted message with a "c" prefix at NORMAL verbosity level.
  template <typename... Args>
  void Log(LogSource source, fmt::format_string<Args...> fmt, Args... args) {
    Log(VerbosityLevel::NORMAL, source, fmt, std::forward<Args>(args)...);
  }

  // Logs a formatted message with a "c" prefix at NORMAL verbosity level from
  // the SOLVER source.
  template <typename... Args>
  void Log(fmt::format_string<Args...> fmt, Args... args) {
    Log(VerbosityLevel::NORMAL, LogSource::SOLVER, fmt,
        std::forward<Args>(args)...);
  }

  // Logs a formatted message with a "c" prefix if the verbosity level allows
  // it, from the SOLVER source.
  template <typename... Args>
  void Log(VerbosityLevel verbosity, fmt::format_string<Args...> fmt,
           Args... args) {
    Log(verbosity, LogSource::SOLVER, fmt, std::forward<Args>(args)...);
  }

  // Logs an output value with an "o" prefix if the verbosity level allows it.
  template <typename Val>
  void LogO(VerbosityLevel verbosity, LogSource source, Val value) {
    LogPrefixed(verbosity, source, "o ", "{}", value);
  }

  // Logs an output value with an "o" prefix at NORMAL verbosity level.
  template <typename Val>
  void LogO(LogSource source, Val value) {
    LogO(VerbosityLevel::NORMAL, source, value);
  }

  // Logs an output value with an "o" prefix at NORMAL verbosity level from
  // the SOLVER source.
  template <typename Val>
  void LogO(Val value) {
    LogO(VerbosityLevel::NORMAL, LogSource::SOLVER, value);
  }

  // Logs a status with an "s" prefix if the verbosity level allows it.
  void LogS(VerbosityLevel verbosity, LogSource source, fmt::string_view str) {
    LogPrefixed(verbosity, source, "s ", "{}", str);
  }

  // Logs a status with an "s" prefix at NORMAL verbosity level.
  void LogS(LogSource source, fmt::string_view str) {
    LogS(VerbosityLevel::NORMAL, source, str);
  }

  // Logs a status with an "s" prefix at NORMAL verbosity level from
  // the SOLVER source.
  void LogS(fmt::string_view str) {
    LogS(VerbosityLevel::NORMAL, LogSource::SOLVER, str);
  }

  // Logs a model with a "v" prefix if the verbosity level allows it.
  void LogV(VerbosityLevel verbosity, LogSource source,
            fmt::string_view model_str) {
    LogPrefixed(verbosity, source, "v ", "{}", model_str);
  }

  // Logs a model with a "v" prefix at NORMAL verbosity level.
  void LogV(LogSource source, fmt::string_view model_str) {
    LogV(VerbosityLevel::NORMAL, source, model_str);
  }

  // Logs a model with a "v" prefix at NORMAL verbosity level from
  // the SOLVER source.
  void LogV(fmt::string_view model_str) {
    LogV(VerbosityLevel::NORMAL, LogSource::SOLVER, model_str);
  }

  // Logs a time value pair with a "c timeo" prefix if the verbosity level
  // allows it.
  template <typename Val>
  void LogTimeO(VerbosityLevel verbosity, LogSource source, Val value) {
    LogPrefixed(verbosity, source, "c timeo ", "{} {}", GetTimeInSeconds(),
                value);
  }

  // Logs a time value pair with a "c timeo" prefix at VERBOSE verbosity level.
  template <typename Val>
  void LogTimeO(LogSource source, Val value) {
    LogTimeO(VerbosityLevel::VERBOSE, source, value);
  }

  // Logs a time value pair with a "c timeo" prefix at VERBOSE verbosity level
  // from the SOLVER source.
  template <typename Val>
  void LogTimeO(Val value) {
    LogTimeO(VerbosityLevel::VERBOSE, LogSource::SOLVER, value);
  }

  // Logs a formatted message with a given prefix.
  template <typename... Args>
  void LogPrefixed(VerbosityLevel verbosity, LogSource source,
                   fmt::string_view prefix, fmt::format_string<Args...> fmt,
                   Args... args) {
    if (verbosity <= source_verbosity_levels_[static_cast<int>(source)]) {
      const auto& text_style =
          cached_styles_[static_cast<int>(source)][static_cast<int>(verbosity)];
      auto message = fmt::format(fmt, std::forward<Args>(args)...);
      fmt::print(text_style, "{}{}\n", prefix, message);
      std::fflush(stdout);
    }
  }

  // TODO: Fix dumping format

  template <typename Val>
  void DumpSpan(std::span<Val> values, bool newline = true) {
    if (dump_temp_disabled_) return;

    for (const auto& val : values) {
      fmt::print(*dump_file_, "{} ", val);
    }
    if (newline) {
      fmt::print(*dump_file_, "0\n");
      dump_file_->flush();
    }
  }

  template <ValidLiteral TLit, ValidWeight TWeight>
  void DumpSpan(WLits<TLit, TWeight> values, bool newline = true) {
    if (dump_temp_disabled_) return;

    for (const auto& [weight, lit] : values) {
      fmt::print(*dump_file_, "{} {} ", weight, lit);
    }
    if (newline) {
      fmt::print(*dump_file_, "0\n");
      dump_file_->flush();
    }
  }

  template <typename Val>
  void DumpPrefixedSpan(std::span<Val> values, char prefix,
                        bool newline = true) {
    if (dump_temp_disabled_) return;

    fmt::print(*dump_file_, "{} ", prefix);
    DumpSpan(values, newline);
  }

  template <typename... Args>
  void DumpPrefixed(char prefix, fmt::format_string<Args...> fmt,
                    Args... args) {
    if (dump_temp_disabled_) return;

    fmt::print(*dump_file_, "{} ", prefix);
    fmt::print(*dump_file_, fmt, std::forward<Args>(args)...);
    fmt::print(*dump_file_, " ");
  }

  template <ValidLiteral TLit>
  void DumpSolve(Lits<TLit> assumps) {
    if (dump_temp_disabled_) return;

    DumpPrefixedSpan(assumps, 's');
  }

  template <ValidLiteral TLit>
  void DumpSolveMaxSAT(Lits<TLit> assumps, Lits<TLit> lits) {
    if (dump_temp_disabled_) return;

    DumpPrefixed('u', "{} {}", assumps.size(), lits.size());
    DumpSpan(assumps, false);
    DumpSpan(lits);
  }

  template <ValidLiteral TLit, ValidWeight TWeight>
  void DumpSolveWeightedMaxSAT(Lits<TLit> assumps, WLits<TLit, TWeight> wlits) {
    if (dump_temp_disabled_) return;

    DumpPrefixed('w', "{} {}", assumps.size(), wlits.size());
    DumpSpan(assumps, false);
    DumpSpan(wlits);
  }

  template <ValidLiteral TLit>
  void DumpSolveBlackBox(Lits<TLit> assumps, Lits<TLit> observables) {
    if (dump_temp_disabled_) return;

    DumpPrefixed('g', "{} {}", assumps.size(), observables.size());
    DumpSpan(assumps, false);
    DumpSpan(observables);
  }

  template <ValidLiteral TLit>
  void DumpSolveOBV(Lits<TLit> assumps, Lits<TLit> targets) {
    if (dump_temp_disabled_) return;

    DumpPrefixed('b', "{} {}", assumps.size(), targets.size());
    DumpSpan(assumps, false);
    DumpSpan(targets);
  }

  template <ValidLiteral TLit>
  void DumpConstraintRHS(Predicate pred, uint64_t rhs,
                         std::optional<TLit> selector = std::nullopt) {
    fmt::string_view pred_str;
    switch (pred) {
      case Predicate::LT:
        pred_str = "<";
        break;
      case Predicate::LEQ:
        pred_str = "<=";
        break;
      case Predicate::EQ:
        pred_str = "=";
        break;
      case Predicate::GEQ:
        pred_str = ">=";
        break;
      case Predicate::GT:
        pred_str = ">";
        break;
    }
    fmt::print(*dump_file_, "{} {} {} 0\n", pred_str, rhs,
               selector.has_value() ? *selector : 0);
    dump_file_->flush();
  }

  template <ValidLiteral TLit>
  void DumpCConstraint(Lits<TLit> lits, Predicate pred, uint64_t rhs,
                       std::optional<TLit> selector = std::nullopt) {
    if (dump_temp_disabled_) return;

    DumpPrefixedSpan(lits, 'd', false);
    DumpConstraintRHS(pred, rhs, selector);
  }

  template <ValidLiteral TLit, ValidWeight TWeight>
  void DumpPBConstraint(WLits<TLit, TWeight> wlits, Predicate pred,
                        uint64_t rhs,
                        std::optional<TLit> selector = std::nullopt) {
    if (dump_temp_disabled_) return;

    fmt::print(*dump_file_, "D ");
    DumpSpan(wlits, false);
    DumpConstraintRHS(pred, rhs, selector);
  }

  template <ValidLiteral TLit>
  void DumpTotalizer(Lits<TLit> lits, TLit selector,
                     std::optional<uint64_t> rhs_simplification) {
    if (dump_temp_disabled_) return;

    DumpPrefixed('t', "{} {}", selector,
                 rhs_simplification.has_value() ? *rhs_simplification : 0);
    DumpSpan(lits);
  }

  template <ValidLiteral TLit, ValidWeight TWeight>
  void DumpGenTotalizer(WLits<TLit, TWeight> wlits, TLit selector,
                        std::optional<uint64_t> rhs_simplification) {
    if (dump_temp_disabled_) return;

    DumpPrefixed('T', "{} {}", selector,
                 rhs_simplification.has_value() ? *rhs_simplification : 0);
    DumpSpan(wlits);
  }

  void DumpNewVar() {
    if (dump_temp_disabled_) return;

    fmt::print(*dump_file_, "n 1 0\n");
    dump_file_->flush();
  }

  void SetVerbosity(LogSource source, VerbosityLevel verbosity) {
    source_verbosity_levels_[static_cast<int>(source)] = verbosity;
    UpdateTextStyles();
  }

  void SetEnableColoring(LogSource source, bool enable) {
    source_use_color_[static_cast<int>(source)] = enable;
    UpdateTextStyles();
  }

  double GetTimeInSeconds() const {
    return std::chrono::duration_cast<std::chrono::seconds>(Clock::now() -
                                                            start_time_)
        .count();
  }

  double GetExactTimeInSeconds() const {
    return std::chrono::duration<double>(Clock::now() - start_time_).count();
  }

  void ResetTimer() { start_time_ = Clock::now(); }

  // Disables dumping temporarily until EnableDump() is called. Useful for
  // skipping dumps during certain phases, e.g. internal API function calls.
  void DisableDumpTemporarily() { dump_temp_disabled_ = true; }
  // Enables dumping after it has been temporarily disabled.
  void EnableDump() { dump_temp_disabled_ = false; }

  inline bool ShouldDump() { return dump_file_ && *dump_file_; }

  Logger(const Logger&) = delete;
  Logger& operator=(const Logger&) = delete;
  Logger(Logger&&) = delete;
  Logger& operator=(Logger&&) = delete;

 private:
  static Logger instance_;
  std::array<VerbosityLevel, 2> source_verbosity_levels_;
  std::array<bool, 2> source_use_color_;
  std::array<std::array<fmt::text_style, 4>, 2> cached_styles_;
  fmt::text_style default_style_;
  Clock::time_point start_time_;
  std::unique_ptr<std::ofstream> dump_file_;
  bool dump_temp_disabled_ = false;

  Logger() : default_style_(fmt::text_style()), start_time_(Clock::now()) {
    source_verbosity_levels_.fill(VerbosityLevel::NORMAL);
    source_use_color_.fill(false);
    UpdateTextStyles();
    const char* dump_file_name = getenv("APERTURE_DUMP_FILE");
    if (dump_file_name != nullptr) {
      InitDumpFile(dump_file_name);
    }
  }
  ~Logger() = default;

  void UpdateTextStyles() {
    auto ComputeTextStyle = [this](LogSource source, VerbosityLevel verbosity) {
      if (!source_use_color_[static_cast<int>(source)]) {
        return default_style_;
      }
      switch (verbosity) {
        case VerbosityLevel::VERBOSE:
          return fmt::fg(fmt::color::steel_blue);
        case VerbosityLevel::VVERBOSE:
          return fmt::fg(fmt::color::dim_gray);
        default:
          return default_style_;
      }
    };

    for (int src = 0; src <= static_cast<int>(LogSource::EXTERNAL); ++src) {
      for (int verb = 0; verb <= static_cast<int>(VerbosityLevel::VVERBOSE);
           ++verb) {
        cached_styles_[src][verb] = ComputeTextStyle(
            static_cast<LogSource>(src), static_cast<VerbosityLevel>(verb));
      }
    }
  }

  void InitDumpFile(const std::string& file_name) {
    std::stringstream ss;

    ss << file_name << "_";

    time_t now;
    time(&now);
    struct tm* current = localtime(&now);

    ss << (void*)this << '_'
#if defined(__MINGW32__)
       << _getpid()
#else
       << getpid()
#endif
       << '_';
    if (current != NULL) {
      ss << current->tm_mday << "." << (current->tm_mon + 1) << "."
         << 1900 + current->tm_year << '_' << current->tm_hour << "_"
         << current->tm_min << "_" << current->tm_sec;
    }
    ss << ".acnf";

    dump_file_.reset(new std::ofstream(ss.str(), std::ofstream::out));
  }
};
};  // namespace Aperture
