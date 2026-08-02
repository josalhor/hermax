#pragma once

#include <functional>
#include <optional>
#include <span>

#include "../ATypes.h"

namespace Aperture {

template <ValidLiteral TLit = int32_t, ValidWeight TWeight = uint64_t>
class Encoder {
 public:
  Encoder(std::function<TLit()> NewVarFunc,
          std::function<bool(Lits<TLit>)> AddClauseFunc)
      : NewVar_(NewVarFunc), AddClause_(AddClauseFunc) {}

 protected:
  std::function<TLit()> NewVar_;
  std::function<bool(Lits<TLit>)> AddClause_;
};
};  // namespace Aperture