#pragma once

#include <string>

#include "../AOptions.h"
#include "../ATypes.h"

namespace Aperture {

class ArgParser {
 public:
  static std::pair<ExternalOptions, SolverOptions> ParseArgs(
      int argc, const char* const* argv);
};
};  // namespace Aperture