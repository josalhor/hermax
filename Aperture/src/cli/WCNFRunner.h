#pragma once

#include "../Aperture.h"
#include "WCNFData.h"

namespace Aperture {

template <ValidLiteral TLit, ValidWeight TWeight>
class WCNFRunner {
 public:
  static int Run(const std::string& wcnf_file_path, SolverType solver_type,
                 SolverOptions& solver_options);

 private:
  inline static Logger& logger = Logger::Instance();
  inline static std::unique_ptr<Solver<TLit, TWeight>> solver;
  inline static TLit max_var;
  inline static ProblemType problem_type;
  inline static SolverStatus solver_return_status;
  inline static constexpr LogSource kExternal =
      LogSource::EXTERNAL;  // Logs from WCNFRunner are external
  inline static constexpr VerbosityLevel kPrintRegardless =
      VerbosityLevel::SILENT;  // For logs regardless of the verbosity level

  static void print_results_and_exit(int signal) {
    if (solver) {
      PrintResults();
      exit(SolverStatusCode());
    }
    exit(0);
  }

  static void Reset();
  static int SolverStatusCode();
  static void PrintProblemStatistics(const WCNFData<TLit, TWeight>& wcnf_data,
                                     double parsing_time_seconds);
  static void PrintModel(std::span<const TLitValue> model);
  static void PrintValue(TWeight value);
  static void PrintResults();
};
};  // namespace Aperture