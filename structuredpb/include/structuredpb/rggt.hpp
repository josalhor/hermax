#ifndef STRUCTUREDPB_RGGT_HPP
#define STRUCTUREDPB_RGGT_HPP

#include "structuredpb/encoder.hpp"

namespace structuredpb {

class RggtEncoder final : public Encoder {
public:
    std::string_view name() const override { return "rggt"; }
    EncodeResult encode(const GroupedLeqConstraint& constraint,
                        const EncodeOptions& options = {}) const override;
};

}  // namespace structuredpb

#endif
