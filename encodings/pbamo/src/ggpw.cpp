#include "structuredpb/ggpw.hpp"

#include <algorithm>
#include <cstdint>
#include <unordered_map>
#include <utility>
#include <vector>

namespace structuredpb {
namespace {

void add_pairwise_amo(const GroupedLeqConstraint& constraint, CnfFormula& cnf) {
    if (!constraint.emit_amo) {
        return;
    }
    for (const auto& group : constraint.groups) {
        for (std::size_t i = 0; i < group.size(); ++i) {
            for (std::size_t j = i + 1; j < group.size(); ++j) {
                cnf.add_clause({-group[i], -group[j]});
            }
        }
    }
}

std::unordered_map<int, Weight> make_weight_map(const GroupedLeqConstraint& constraint) {
    std::unordered_map<int, Weight> out;
    out.reserve(constraint.terms.size());
    for (const auto& term : constraint.terms) {
        out.emplace(term.lit, term.weight);
    }
    return out;
}

std::size_t bit_length(Weight value) {
    std::size_t bits = 0;
    do {
        ++bits;
        value >>= 1U;
    } while (value != 0);
    return bits;
}

int bit_at(Weight value, std::size_t r) {
    return static_cast<int>((value >> r) & static_cast<Weight>(1));
}

Weight pow2(std::size_t r) {
    return static_cast<Weight>(1) << r;
}

std::vector<int> totalizer_merge(
    const std::vector<int>& left,
    const std::vector<int>& right,
    VariableManager& vm,
    CnfFormula& cnf) {
    const std::size_t out_size = left.size() + right.size();
    if (out_size == 0) {
        return {};
    }
    std::vector<int> out(out_size, 0);
    for (std::size_t i = 0; i < out_size; ++i) {
        out[i] = vm.new_var();
    }

    for (std::size_t i = 0; i < left.size(); ++i) {
        cnf.add_clause({-left[i], out[i]});
    }
    for (std::size_t j = 0; j < right.size(); ++j) {
        cnf.add_clause({-right[j], out[j]});
    }
    for (std::size_t i = 0; i < left.size(); ++i) {
        for (std::size_t j = 0; j < right.size(); ++j) {
            cnf.add_clause({-left[i], -right[j], out[i + j + 1]});
        }
    }
    return out;
}

std::vector<int> totalizer_encode(std::vector<int> vars, VariableManager& vm, CnfFormula& cnf) {
    if (vars.empty()) {
        return {};
    }
    if (vars.size() == 1) {
        return vars;
    }
    std::vector<std::vector<int>> layers;
    layers.reserve(vars.size());
    for (int lit : vars) {
        layers.push_back({lit});
    }
    while (layers.size() > 1) {
        std::vector<std::vector<int>> next;
        next.reserve((layers.size() + 1) / 2);
        for (std::size_t i = 0; i < layers.size(); i += 2) {
            if (i + 1 == layers.size()) {
                next.push_back(std::move(layers[i]));
            } else {
                next.push_back(totalizer_merge(layers[i], layers[i + 1], vm, cnf));
            }
        }
        layers = std::move(next);
    }
    return std::move(layers[0]);
}

}  // namespace

EncodeResult GgpwEncoder::encode(const GroupedLeqConstraint& constraint,
                                 const EncodeOptions& options) const {
    constraint.validate();

    EncodeResult result;
    VariableManager vm(options.top_id);
    result.cnf.num_vars = options.top_id;
    add_pairwise_amo(constraint, result.cnf);
    const auto weights = make_weight_map(constraint);

    Weight qmax = 0;
    for (const auto& term : constraint.terms) {
        qmax = std::max(qmax, term.weight);
    }
    const std::size_t bits = bit_length(qmax);
    const std::size_t p = bits - 1;
    const Weight bucket_scale = pow2(p);
    const Weight k1 = constraint.bound + 1;
    const Weight rem = k1 % bucket_scale;
    const Weight t = rem == 0 ? 0 : (bucket_scale - rem);
    const Weight target = k1 + t;
    const Weight m = target / bucket_scale;

    int true_var = 0;
    auto make_true_var = [&]() -> int {
        if (true_var == 0) {
            true_var = vm.new_var();
            result.cnf.add_clause({true_var});
        }
        return true_var;
    };

    std::vector<std::vector<int>> bucket_vars(p + 1);
    for (std::size_t gi = 0; gi < constraint.groups.size(); ++gi) {
        const auto& group = constraint.groups[gi];
        for (std::size_t r = 0; r <= p; ++r) {
            std::vector<int> sources;
            for (int lit : group) {
                if (bit_at(weights.at(lit), r) == 1) {
                    sources.push_back(lit);
                }
            }
            if (sources.empty()) {
                continue;
            }
            if (sources.size() == 1) {
                bucket_vars[r].push_back(sources[0]);
                continue;
            }
            const int y = vm.new_var();
            for (int lit : sources) {
                result.cnf.add_clause({-lit, y});
            }
            bucket_vars[r].push_back(y);
        }
    }
    for (std::size_t r = 0; r <= p; ++r) {
        if (bit_at(t, r) == 1) {
            bucket_vars[r].push_back(make_true_var());
        }
    }

    std::vector<int> prev_sum;
    std::vector<int> current_sum;
    for (std::size_t r = 0; r <= p; ++r) {
        std::vector<int> inputs = bucket_vars[r];
        if (!prev_sum.empty()) {
            for (std::size_t idx = 1; idx < prev_sum.size(); idx += 2) {
                inputs.push_back(prev_sum[idx]);
            }
        }
        current_sum = totalizer_encode(std::move(inputs), vm, result.cnf);
        prev_sum = current_sum;
    }

    if (m > 0 && current_sum.size() >= static_cast<std::size_t>(m)) {
        result.cnf.add_clause({-current_sum[static_cast<std::size_t>(m - 1)]});
    }

    result.cnf.num_vars = std::max(result.cnf.num_vars, vm.max_var());
    result.stats.auxiliary_variables = static_cast<std::size_t>(result.cnf.num_vars - options.top_id);
    result.stats.clauses = result.cnf.clauses.size();
    return result;
}

}  // namespace structuredpb
