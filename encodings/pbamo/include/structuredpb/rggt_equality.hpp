#ifndef STRUCTUREDPB_RGGT_EQUALITY_HPP
#define STRUCTUREDPB_RGGT_EQUALITY_HPP

#include "structuredpb/encoder.hpp"

namespace structuredpb {

// The grouped weighted-sum representation is shared with <=, but the tree's
// domains and clauses are built specifically for equality.
EncodeResult encode_rggt_equality(const GroupedLeqConstraint& sum,
                                  const EncodeOptions& options = {});

}  // namespace structuredpb

#endif
