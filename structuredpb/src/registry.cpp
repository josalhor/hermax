#include "structuredpb/encoder.hpp"

#include <stdexcept>

#include "structuredpb/ggpw.hpp"
#include "structuredpb/gmto.hpp"
#include "structuredpb/gswc.hpp"
#include "structuredpb/mdd.hpp"
#include "structuredpb/rggt.hpp"

namespace structuredpb {

std::unique_ptr<Encoder> make_encoder(std::string_view name) {
    if (name == "mdd") {
        return std::make_unique<MddEncoder>();
    }
    if (name == "gswc") {
        return std::make_unique<GswcEncoder>();
    }
    if (name == "ggpw") {
        return std::make_unique<GgpwEncoder>();
    }
    if (name == "gmto") {
        return std::make_unique<GmtoEncoder>();
    }
    if (name == "rggt") {
        return std::make_unique<RggtEncoder>();
    }
    throw std::invalid_argument("structuredpb: unknown encoder name");
}

std::vector<std::string> available_encoders() {
    return {"mdd", "gswc", "ggpw", "gmto", "rggt"};
}

}  // namespace structuredpb
