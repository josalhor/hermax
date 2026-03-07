#pragma once

#if defined(USE_CADICAL)

// CaDiCaL build: include the wrapper UWrMaxSat expects
#include "../uwrmaxsat/CadicalWrap.h"
// Also include UWr’s vector template definition
#include "../uwrmaxsat/ADTs/Global.h"

// Some UWr files still spell 'Minisat::vec<...>'.
// Provide a minimal alias to UWr's vec so those compile in CaDiCaL mode.
namespace Minisat {
    template <typename T> using vec = ::vec<T>;
    // If any file ever refers to Minisat::Lit by mistake, map it to UWr/CaDiCaL Lit.
    using Lit = ::Lit;
    // (We don't alias lbool etc. here because UWr doesn’t need it in CaDiCaL mode.)
}

#else

// MiniSat / COMiniSatPS compatibility mode
#include "minisat/core/SolverTypes.h"
#include "minisat/simp/SimpSolver.h"

namespace COMinisatPS {
    using namespace Minisat;
}
namespace Minisat = COMinisatPS;

using COMinisatPS::Lit;
using COMinisatPS::lbool;
using COMinisatPS::Var;
using COMinisatPS::vec;
using COMinisatPS::SimpSolver;
using COMinisatPS::ExtSimpSolver;

#endif
