#include "aperture_native.h"
#include "src/ipamir/AIpamirWrapper.h"
#include <memory>
struct ApertureBackend::Impl {
    using Solver = Aperture::ApertureIpamir<int32_t, uint64_t>;
    std::unique_ptr<Solver> solver;
    Impl() {
        auto &logger = Aperture::Logger::Instance();
        logger.SetVerbosity(Aperture::LogSource::SOLVER, Aperture::VerbosityLevel::SILENT);
        logger.SetVerbosity(Aperture::LogSource::EXTERNAL, Aperture::VerbosityLevel::SILENT);
        Aperture::SolverOptions options;
        options.verbosity_level = Aperture::VerbosityLevel::SILENT;
        solver = std::make_unique<Solver>(options);
    }
};
ApertureBackend::ApertureBackend() : impl_(new Impl()) {}
ApertureBackend::~ApertureBackend() { delete impl_; }
int ApertureBackend::new_var() {
    impl_->solver->NewVar();
    return impl_->solver->MaxVar();
}
void ApertureBackend::add_clause(const std::vector<int32_t> &c) {
    for (int32_t lit : c)
        impl_->solver->AddHard(lit);
    impl_->solver->AddHard(0);
}
void ApertureBackend::set_soft(int32_t lit, uint64_t weight) {
    impl_->solver->AddSoftLit(lit, weight);
}
void ApertureBackend::assume(int32_t lit) { impl_->solver->Assume(lit); }
int ApertureBackend::solve() { return impl_->solver->Solve(); }
uint64_t ApertureBackend::objective_value() const { return impl_->solver->GetObjectiveValue(); }
int32_t ApertureBackend::value(int32_t lit) const { return impl_->solver->GetLitValue(lit); }
const char *ApertureBackend::signature() const { return "Aperture"; }
