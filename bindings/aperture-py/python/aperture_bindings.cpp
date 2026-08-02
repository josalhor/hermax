#include <cstdint>
#include <memory>
#include <stdexcept>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "src/ipamir/AIpamirWrapper.h"

namespace py = pybind11;

class ApertureBackend {
 public:
  ApertureBackend() : solver_(std::make_unique<Solver>()) {}

  int new_var() {
    solver_->NewVar();
    return solver_->MaxVar();
  }

  void add_clause(const std::vector<int32_t>& clause) {
    for (int32_t lit : clause) solver_->AddHard(lit);
    solver_->AddHard(0);
  }

  void set_soft(int32_t lit, uint64_t weight) { solver_->AddSoftLit(lit, weight); }
  void assume(int32_t lit) { solver_->Assume(lit); }
  int solve() { return solver_->Solve(); }
  uint64_t objective_value() const { return solver_->GetObjectiveValue(); }
  int32_t value(int32_t lit) const { return solver_->GetLitValue(lit); }
  const char* signature() const { return "Aperture"; }

 private:
  using Solver = Aperture::ApertureIpamir<int32_t, uint64_t>;
  std::unique_ptr<Solver> solver_;
};

PYBIND11_MODULE(_aperture_native, m) {
  m.doc() = "Hermax native bridge for Aperture's IPAMIR implementation";
  py::class_<ApertureBackend>(m, "Aperture")
      .def(py::init<>())
      .def("new_var", &ApertureBackend::new_var)
      .def("add_clause", &ApertureBackend::add_clause)
      .def("set_soft", &ApertureBackend::set_soft)
      .def("assume", &ApertureBackend::assume)
      .def("solve", &ApertureBackend::solve)
      .def("objective_value", &ApertureBackend::objective_value)
      .def("value", &ApertureBackend::value)
      .def("signature", &ApertureBackend::signature);
}
