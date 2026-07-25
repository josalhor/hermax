#pragma once

#include "../Aperture.h"

namespace Aperture {

template <ValidLiteral TLit, ValidWeight TWeight>
class ACNFRunner {
 public:
  static int Run(const std::string& acnf_file_path, SolverType solver_type,
                 bool strict_user_vars, SolverOptions& solver_options);

 private:
  inline static Logger& logger = Logger::Instance();
  inline static std::unique_ptr<Solver<TLit, TWeight>> solver;
  inline static std::vector<TLit> user_vars;
  inline static ProblemType problem_type;
  inline static SolverStatus solver_return_status;
  inline static constexpr LogSource kExternal =
      LogSource::EXTERNAL;  // Logs from ACNFRunner are external
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
  static void PrintSolvingMessage(ProblemType problem_type,
                                  size_t num_assumptions,
                                  size_t num_literals = 0);
  static void PrintModel(std::span<const TLitValue> model);
  static void PrintValue(TWeight value);
  static void PrintResults();
};
};  // namespace Aperture