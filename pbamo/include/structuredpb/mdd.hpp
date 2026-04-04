#ifndef STRUCTUREDPB_MDD_HPP
#define STRUCTUREDPB_MDD_HPP

#include "structuredpb/encoder.hpp"

namespace structuredpb {

class MddEncoder final : public Encoder {
public:
    std::string_view name() const override { return "mdd"; }
    EncodeResult encode(const GroupedLeqConstraint& constraint,
                        const EncodeOptions& options = {}) const override;
};

}  // namespace structuredpb

#endif
