#ifndef STRUCTUREDPB_GSWC_HPP
#define STRUCTUREDPB_GSWC_HPP

#include "structuredpb/encoder.hpp"

namespace structuredpb {

class GswcEncoder final : public Encoder {
public:
    std::string_view name() const override { return "gswc"; }
    EncodeResult encode(const GroupedLeqConstraint& constraint,
                        const EncodeOptions& options = {}) const override;
};

}  // namespace structuredpb

#endif
