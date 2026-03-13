#ifndef STRUCTUREDPB_ENCODER_HPP
#define STRUCTUREDPB_ENCODER_HPP

#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include "structuredpb/cnf.hpp"
#include "structuredpb/types.hpp"

namespace structuredpb {

struct EncodeOptions {
    int top_id = 0;
};

struct EncodeStats {
    std::size_t auxiliary_variables = 0;
    std::size_t clauses = 0;
};

struct EncodeResult {
    CnfFormula cnf;
    EncodeStats stats;
};

class Encoder {
public:
    virtual ~Encoder() = default;
    virtual std::string_view name() const = 0;
    virtual EncodeResult encode(const GroupedLeqConstraint& constraint,
                                const EncodeOptions& options = {}) const = 0;
};

std::unique_ptr<Encoder> make_encoder(std::string_view name);
std::vector<std::string> available_encoders();

}  // namespace structuredpb

#endif
