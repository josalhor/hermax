#include "../../contrib/craigtracer.hpp"
#include "../../src/cadical.hpp"

#ifdef NDEBUG
#undef NDEBUG
#endif

#include <cassert>
#include <vector>

int main () {
  ApertureCaDiCaL::Solver *solver = new ApertureCaDiCaL::Solver ();
  solver->set ("factor", 0); // important: deactivate BVA
  ApertureCaDiCraig::CraigTracer *tracer =
      new ApertureCaDiCraig::CraigTracer ();
  solver->connect_proof_tracer (tracer, true);
  tracer->set_craig_construction (
      ApertureCaDiCraig::CraigConstruction::ASYMMETRIC);

  tracer->label_variable (1, ApertureCaDiCraig::CraigVarType::GLOBAL);
  tracer->label_clause (1, ApertureCaDiCraig::CraigClauseType::A_CLAUSE);
  tracer->label_clause (2, ApertureCaDiCraig::CraigClauseType::B_CLAUSE);
  solver->set ("factor", 0);
  solver->add (-1);
  solver->add (0);
  solver->add (1);
  solver->add (0);
  assert (solver->solve () == ApertureCaDiCaL::Status::UNSATISFIABLE);

  int next_var = 2;
  std::vector<std::vector<int>> clauses;
  ApertureCaDiCraig::CraigCnfType result =
      tracer->create_craig_interpolant (
          ApertureCaDiCraig::CraigInterpolant::ASYMMETRIC, clauses,
          next_var);
  assert (result == ApertureCaDiCraig::CraigCnfType::NORMAL);
  assert (clauses == std::vector<std::vector<int>>{{-1}});
  assert (next_var == 2);

  solver->disconnect_proof_tracer (tracer);
  delete tracer;
  delete solver;

  return 0;
}
