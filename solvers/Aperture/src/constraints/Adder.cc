#include "Adder.h"

#include <iostream>
#include <queue>

using namespace std;
using namespace Aperture;

template <ValidLiteral TLit, ValidWeight TWeight>
AdderBits<TLit> Adder<TLit, TWeight>::EncodeAdder(WLits<TLit, TWeight> wlits,
                                                  optional<TLit> selector) {
  constexpr size_t kNumBitsInWeight = sizeof(TWeight) * 8;
  vector<queue<TLit>> buckets(kNumBitsInWeight + 1);
  AdderBits<TLit> output;

  // Fill buckets
  TWeight mask;
  for (const auto& [weight, lit] : wlits) {
    mask = 1;
    for (size_t i = 0; i < kNumBitsInWeight; i++) {
      if (weight & mask) {
        buckets[i].push(lit);
      }
      mask <<= 1;
    }
  }

  auto FullAdderSum = [&](TLit x, TLit y, TLit z) {
    TLit s = this->NewVar_();

    AddQuadClause(-x, -y, -z, s, selector);
    AddQuadClause(-x, y, z, s, selector);
    AddQuadClause(x, -y, z, s, selector);
    AddQuadClause(x, y, -z, s, selector);

    AddQuadClause(x, y, z, -s, selector);
    AddQuadClause(x, -y, -z, -s, selector);
    AddQuadClause(-x, y, -z, -s, selector);
    AddQuadClause(-x, -y, z, -s, selector);

    return s;
  };

  auto FullAdderCarry = [&](TLit x, TLit y, TLit z) {
    TLit c = this->NewVar_();

    AddTernaryClause(-y, -z, c, selector);
    AddTernaryClause(-x, -z, c, selector);
    AddTernaryClause(-x, -y, c, selector);

    AddTernaryClause(y, z, -c, selector);
    AddTernaryClause(x, z, -c, selector);
    AddTernaryClause(x, y, -c, selector);

    return c;
  };

  auto HalfAdderSum = [&](TLit x, TLit y) {
    TLit s = this->NewVar_();

    AddTernaryClause(-x, y, s, selector);
    AddTernaryClause(x, -y, s, selector);

    AddTernaryClause(-x, -y, -s, selector);
    AddTernaryClause(x, y, -s, selector);

    return s;
  };

  auto HalfAdderCarry = [&](TLit x, TLit y) {
    TLit c = this->NewVar_();

    AddBinaryClause(x, -c, selector);
    AddBinaryClause(y, -c, selector);
    AddTernaryClause(-x, -y, c, selector);

    return c;
  };

  // Encode adders tree
  for (size_t i = 0; i < buckets.size() - 1; i++) {
    if (buckets[i].empty()) continue;

    while (buckets[i].size() >= 3) {
      TLit x = buckets[i].front();
      buckets[i].pop();
      TLit y = buckets[i].front();
      buckets[i].pop();
      TLit z = buckets[i].front();
      buckets[i].pop();
      // buckets[i] <- FA_sum
      buckets[i].push(FullAdderSum(x, y, z));
      // buckets[i+1] <- FA_carry
      buckets[i + 1].push(FullAdderCarry(x, y, z));
    }
    if (buckets[i].size() == 2) {
      TLit x = buckets[i].front();
      buckets[i].pop();
      TLit y = buckets[i].front();
      buckets[i].pop();
      // buckets[i] <- HA_sum
      buckets[i].push(HalfAdderSum(x, y));
      // buckets[i+1] <- HA_carry
      buckets[i + 1].push(HalfAdderCarry(x, y));
    }
    output.InsertBit(buckets[i].front(), i);
    buckets[i].pop();
  }

  return output;
}

template <ValidLiteral TLit, ValidWeight TWeight>
AdderBits<TLit> Adder<TLit, TWeight>::LessThanOrEqualBits(
    AdderBits<TLit> adder_bits, optional<TLit> selector) {
  const size_t adder_size = adder_bits.size();

  if (adder_size == 0) return {};

  AdderBits<TLit> output{};

  TLit bound_bits[adder_size];
  for (size_t i = 0; i < adder_size; i++) {
    bound_bits[i] = this->NewVar_();
    output.InsertBit(bound_bits[i], adder_bits.RealIndex(i));
  }

  TLit prefix_bits[adder_size];
  for (size_t i = 0; i < adder_size; i++) {
    prefix_bits[i] = this->NewVar_();
  }

  for (size_t i = 0; i < adder_size - 1; i++) {
    // p_i -> p_{i+1}
    AddBinaryClause(-prefix_bits[i], prefix_bits[i + 1], selector);
    // p_i -> (a_{i+1} <-> b_{i+1})
    AddTernaryClause(-prefix_bits[i], -adder_bits[i + 1], bound_bits[i + 1],
                     selector);
    AddTernaryClause(-prefix_bits[i], adder_bits[i + 1], -bound_bits[i + 1],
                     selector);
    // (a_{i+1} <-> b_{i+1}) /\ p_{i+1} -> p_i
    AddQuadClause(adder_bits[i + 1], bound_bits[i + 1], -prefix_bits[i + 1],
                  prefix_bits[i], selector);
    AddQuadClause(-adder_bits[i + 1], -bound_bits[i + 1], -prefix_bits[i + 1],
                  prefix_bits[i], selector);
    // p_i -> (a_i -> b_i)
    AddTernaryClause(-prefix_bits[i], -adder_bits[i], bound_bits[i], selector);
  }
  // p_{n-1} = true
  if (!selector.has_value()) {
    TLit clause[] = {prefix_bits[adder_size - 1]};
    this->AddClause_(clause);
  } else {
    TLit clause[] = {prefix_bits[adder_size - 1], selector.value()};
    this->AddClause_(clause);
  }
  // p_{n-1} -> (a_{n-1} -> b_{n-1})
  AddTernaryClause(-prefix_bits[adder_size - 1], -adder_bits[adder_size - 1],
                   bound_bits[adder_size - 1], selector);

  return output;
}

template <ValidLiteral TLit, ValidWeight TWeight>
AdderBits<TLit> Adder<TLit, TWeight>::LessThanOrEqualBits(
    WLits<TLit, TWeight> wlits, optional<TLit> selector) {
  AdderBits<TLit> adder_bits = EncodeAdder(wlits, selector);
  return LessThanOrEqualBits(adder_bits, selector);
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Adder<TLit, TWeight>::UpdateLEQBound(AdderBits<TLit>& bound_bits,
                                          TWeight bound_weight) {
  for (size_t i = 0; i < bound_bits.size(); i++) {
    if (bound_weight & (1UL << bound_bits.RealIndex(i))) {
      if (bound_bits[i] < 0) bound_bits[i] = -bound_bits[i];
    } else {
      if (bound_bits[i] > 0) bound_bits[i] = -bound_bits[i];
    }
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
bool Adder<TLit, TWeight>::AddBinaryClause(TLit a, TLit b,
                                           optional<TLit> selector) {
  if (!selector.has_value()) {
    TLit clause[] = {a, b};
    return this->AddClause_(clause);
  } else {
    TLit clause[] = {a, b, selector.value()};
    return this->AddClause_(clause);
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
bool Adder<TLit, TWeight>::AddTernaryClause(TLit a, TLit b, TLit c,
                                            optional<TLit> selector) {
  if (!selector.has_value()) {
    TLit clause[] = {a, b, c};
    return this->AddClause_(clause);
  } else {
    TLit clause[] = {a, b, c, selector.value()};
    return this->AddClause_(clause);
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
bool Adder<TLit, TWeight>::AddQuadClause(TLit a, TLit b, TLit c, TLit d,
                                         optional<TLit> selector) {
  if (!selector.has_value()) {
    TLit clause[] = {a, b, c, d};
    return this->AddClause_(clause);
  } else {
    TLit clause[] = {a, b, c, d, selector.value()};
    return this->AddClause_(clause);
  }
}

template class Aperture::Adder<int32_t, uint64_t>;