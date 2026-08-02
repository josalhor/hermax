#pragma once

#include "Encoder.h"

namespace Aperture {

template <ValidLiteral TLit = int32_t, ValidWeight TWeight = uint64_t>
class Totalizer : public Encoder<TLit, TWeight> {
 public:
  Totalizer(std::function<TLit()> NewVarFunc,
            std::function<bool(Lits<TLit>)> AddClauseFunc)
      : Encoder<TLit, TWeight>(NewVarFunc, AddClauseFunc) {}

  std::vector<TLit> EncodeTotalizer(
      Lits<TLit> wlits, std::optional<TLit> selector = std::nullopt,
      std::optional<uint64_t> rhs_simplification = std::nullopt,
      bool leq_simplification = false);
  std::vector<std::pair<TWeight, TLit>> EncodeGenTotalizer(
      WLits<TLit, TWeight> wlits, std::optional<TLit> selector = std::nullopt,
      std::optional<uint64_t> rhs_simplification = std::nullopt);

  static bool IsLeqTotExceedsThr(Lits<TLit> lits,
                                 std::optional<uint64_t> rhs_simplification,
                                 uint64_t clauses_threshold);
  static bool IsLeqGenTotExceedsThr(WLits<TLit, TWeight> wlits,
                                    std::optional<uint64_t> rhs_simplification,
                                    uint64_t clauses_threshold);
};
};  // namespace Aperture