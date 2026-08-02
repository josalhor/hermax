#include "../Aperture.h"

using namespace std;
using namespace Aperture;

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::LocalSearchMaxSAT(
    Lits<TLit> assumps, WLits<TLit, TWeight> wlits,
    function<bool()> ShouldExitAfterSolutionFound) {
  switch (solver_options_.local_search_solver_type) {
    case LocalSearchSolverType::DEEPDIST:
      DeepDist(assumps, wlits, ShouldExitAfterSolutionFound);
      break;
    case LocalSearchSolverType::NUWLS:
      NuWLS(assumps, wlits, ShouldExitAfterSolutionFound);
      break;
    case LocalSearchSolverType::BAND:
    default:
      NuWeighting(assumps, wlits, ShouldExitAfterSolutionFound);
      break;
  }
}

template class Aperture::Solver<int32_t, uint64_t>;