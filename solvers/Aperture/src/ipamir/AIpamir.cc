#include "AIpamir.h"

#include "AIpamirWrapper.h"

using namespace Aperture;

// Use IPAMIR Types
using TIpamirLit = int32_t;
using TIpamirWeight = uint64_t;

const char* ipamir_signature() { return "Aperture"; }

void* ipamir_init() { return new ApertureIpamir<TIpamirLit, TIpamirWeight>(); }

void ipamir_release(void* solver) {
  auto* ipamir_solver =
      reinterpret_cast<ApertureIpamir<TIpamirLit, TIpamirWeight>*>(solver);
  delete ipamir_solver;
}

void ipamir_add_hard(void* solver, int32_t lit_or_zero) {
  auto* ipamir_solver =
      reinterpret_cast<ApertureIpamir<TIpamirLit, TIpamirWeight>*>(solver);
  ipamir_solver->AddHard(lit_or_zero);
}

void ipamir_add_soft_lit(void* solver, int32_t lit, uint64_t weight) {
  auto* ipamir_solver =
      reinterpret_cast<ApertureIpamir<TIpamirLit, TIpamirWeight>*>(solver);
  ipamir_solver->AddSoftLit(lit, weight);
}

void ipamir_assume(void* solver, int32_t lit) {
  auto* ipamir_solver =
      reinterpret_cast<ApertureIpamir<TIpamirLit, TIpamirWeight>*>(solver);
  ipamir_solver->Assume(lit);
}

int ipamir_solve(void* solver) {
  auto* ipamir_solver =
      reinterpret_cast<ApertureIpamir<TIpamirLit, TIpamirWeight>*>(solver);
  return ipamir_solver->Solve();
}

uint64_t ipamir_val_obj(void* solver) {
  auto* ipamir_solver =
      reinterpret_cast<ApertureIpamir<TIpamirLit, TIpamirWeight>*>(solver);
  return ipamir_solver->GetObjectiveValue();
}

int32_t ipamir_val_lit(void* solver, int32_t lit) {
  auto* ipamir_solver =
      reinterpret_cast<ApertureIpamir<TIpamirLit, TIpamirWeight>*>(solver);
  return ipamir_solver->GetLitValue(lit);
}

void ipamir_set_terminate(void* solver, void* state,
                          int (*terminate)(void* state)) {
  auto* ipamir_solver =
      reinterpret_cast<ApertureIpamir<TIpamirLit, TIpamirWeight>*>(solver);
  ipamir_solver->SetTerminate(state, terminate);
}
