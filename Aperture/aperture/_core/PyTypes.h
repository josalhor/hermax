#pragma once

#include <nanobind/nanobind.h>
#include <nanobind/stl/bind_vector.h>
#include <nanobind/stl/function.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/string.h>

using TLit = int32_t;
using TWeight = uint64_t;
using TWLit = std::pair<TWeight, TLit>;

struct TLiterals : public std::vector<TLit> {
  using std::vector<TLit>::vector;

  TLiterals(std::vector<TLit>&& lits) : std::vector<TLit>(std::move(lits)) {}
};
struct TWLiterals : public std::vector<TWLit> {
  using std::vector<TWLit>::vector;

  TWLiterals(std::vector<TWLit>&& wlits)
      : std::vector<TWLit>(std::move(wlits)) {}
};
