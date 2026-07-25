#pragma once

#include "Encoder.h"

namespace Aperture {

template <ValidLiteral TLit>
class AdderBits {
 public:
  void InsertBit(TLit bit, int16_t real_index) {
    bits.push_back(bit);
    real_index_mapping.push_back(real_index);
  }

  const std::vector<TLit>& Bits() const { return bits; }

  inline size_t size() const { return bits.size(); }
  inline const TLit& operator[](size_t i) const { return bits[i]; }
  inline TLit& operator[](size_t i) { return bits[i]; }
  inline int16_t RealIndex(size_t i) const { return real_index_mapping[i]; }

 private:
  std::vector<TLit> bits;
  std::vector<int16_t> real_index_mapping;
};

template <ValidLiteral TLit = int32_t, ValidWeight TWeight = uint64_t>
class Adder : public Encoder<TLit, TWeight> {
 public:
  Adder(std::function<TLit()> NewVarFunc,
        std::function<bool(Lits<TLit>)> AddClauseFunc)
      : Encoder<TLit, TWeight>(NewVarFunc, AddClauseFunc) {}

  AdderBits<TLit> EncodeAdder(WLits<TLit, TWeight> wlits,
                              std::optional<TLit> selector = std::nullopt);
  AdderBits<TLit> LessThanOrEqualBits(
      AdderBits<TLit> adder_bits, std::optional<TLit> selector = std::nullopt);
  AdderBits<TLit> LessThanOrEqualBits(
      WLits<TLit, TWeight> wlits, std::optional<TLit> selector = std::nullopt);

  static void UpdateLEQBound(AdderBits<TLit>& bound_bits, TWeight bound_weight);

 private:
  bool AddBinaryClause(TLit a, TLit b,
                       std::optional<TLit> selector = std::nullopt);
  bool AddTernaryClause(TLit a, TLit b, TLit c,
                        std::optional<TLit> selector = std::nullopt);
  bool AddQuadClause(TLit a, TLit b, TLit c, TLit d,
                     std::optional<TLit> selector = std::nullopt);
};
};  // namespace Aperture