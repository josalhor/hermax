#include "AOptions.h"
#include "Aperture.h"
#include "cli/ACNFRunner.h"
#include "cli/ArgParser.h"
#include "cli/WCNFRunner.h"
#include "logging/Logger.h"

using namespace std;
using namespace Aperture;
using TLit = int32_t;
using TWeight = uint64_t;

Logger& logger = Logger::Instance();
constexpr LogSource kExternal =
    LogSource::EXTERNAL;  // Logs from Main are external

int main(int argc, char** argv) {
  // Parameter parsing

  auto [external_options, solver_options] = ArgParser::ParseArgs(argc, argv);

  logger.SetVerbosity(kExternal, solver_options.verbosity_level);

  logger.Log(kExternal, "Aperture MaxSAT Solver");
  logger.Log(kExternal, "Author: Yam Slonimski");

  // Running

  switch (external_options.mode) {
    case SolverMode::ACNF:
      logger.Log(kExternal, "Operating in ACNF mode.");
      return ACNFRunner<TLit, TWeight>::Run(
          external_options.input_file, external_options.solver_type,
          external_options.strict_user_vars, solver_options);
    case SolverMode::WCNF:
    default:
      solver_options.wcnf_mode = true;
      logger.Log(kExternal, "Operating in WCNF mode.");
      return WCNFRunner<TLit, TWeight>::Run(external_options.input_file,
                                            external_options.solver_type,
                                            solver_options);
  }
}