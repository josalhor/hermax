#ifndef STRUCTUREDPB_GLPW_HPP
#define STRUCTUREDPB_GLPW_HPP

#include "structuredpb/encoder.hpp"

namespace structuredpb {

class GlpwEncoder final : public Encoder {
public:
    std::string_view name() const override { return "glpw"; }
    EncodeResult encode(const GroupedLeqConstraint& constraint,
                        const EncodeOptions& options = {}) const override;
};

}  // namespace structuredpb

#endif
