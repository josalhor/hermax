#ifndef STRUCTUREDPB_GGPW_HPP
#define STRUCTUREDPB_GGPW_HPP

#include "structuredpb/encoder.hpp"

namespace structuredpb {

class GgpwEncoder final : public Encoder {
public:
    std::string_view name() const override { return "ggpw"; }
    EncodeResult encode(const GroupedLeqConstraint& constraint,
                        const EncodeOptions& options = {}) const override;
};

}  // namespace structuredpb

#endif
