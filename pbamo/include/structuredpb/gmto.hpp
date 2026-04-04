#ifndef STRUCTUREDPB_GMTO_HPP
#define STRUCTUREDPB_GMTO_HPP

#include "structuredpb/encoder.hpp"

namespace structuredpb {

class GmtoEncoder final : public Encoder {
public:
    std::string_view name() const override { return "gmto"; }
    EncodeResult encode(const GroupedLeqConstraint& constraint,
                        const EncodeOptions& options = {}) const override;
};

}  // namespace structuredpb

#endif
