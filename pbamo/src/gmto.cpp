#include "structuredpb/gmto.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace structuredpb {
namespace {

struct DigitList {
    std::vector<int> indices;
    std::unordered_map<int, int> lit_by_index;
};

struct Node {
    bool leaf = false;
    Node* left = nullptr;
    Node* right = nullptr;
    std::vector<DigitList> digits;
    std::vector<int> carries;
};

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

std::vector<std::vector<int>> preprocess_groups(const GroupedLeqConstraint& constraint,
                                                const std::unordered_map<int, Weight>& weight_by_lit,
                                                CnfFormula& cnf) {
    std::vector<std::vector<int>> groups;
    groups.reserve(constraint.groups.size());
    for (const auto& group : constraint.groups) {
        std::vector<int> filtered;
        filtered.reserve(group.size());
        for (int lit : group) {
            const auto it = weight_by_lit.find(lit);
            if (it == weight_by_lit.end()) {
                throw std::invalid_argument("structuredpb: literal missing weight in gmto preprocess");
            }
            if (it->second > constraint.bound) {
                cnf.add_clause({-lit});
                continue;
            }
            filtered.push_back(lit);
        }
        if (!filtered.empty()) {
            groups.push_back(std::move(filtered));
        }
    }
    return groups;
}

Weight grouped_capacity(const std::vector<std::vector<int>>& groups,
                        const std::unordered_map<int, Weight>& weight_by_lit) {
    Weight total = 0;
    for (const auto& group : groups) {
        Weight best = 0;
        for (int lit : group) {
            const auto it = weight_by_lit.find(lit);
            if (it == weight_by_lit.end()) {
                throw std::invalid_argument("structuredpb: missing literal in grouped_capacity");
            }
            best = std::max(best, it->second);
        }
        if (std::numeric_limits<Weight>::max() - total < best) {
            return std::numeric_limits<Weight>::max();
        }
        total += best;
    }
    return total;
}

std::vector<int> weight_digits(Weight value, const std::vector<int>& base) {
    const std::size_t beta = base.size();
    std::vector<int> digits(beta + 1, 0);
    Weight q = value;
    for (std::size_t h = 0; h < beta; ++h) {
        const Weight lambda = static_cast<Weight>(base[h]);
        digits[h] = static_cast<int>(q % lambda);
        q /= lambda;
    }
    digits[beta] = static_cast<int>(q);
    return digits;
}

std::vector<int> select_base_greedy(const GroupedLeqConstraint& constraint) {
    std::vector<int> base;
    if (constraint.bound <= 1) {
        return base;
    }

    std::vector<Weight> reduced;
    reduced.reserve(constraint.terms.size());
    for (const auto& term : constraint.terms) {
        reduced.push_back(term.weight);
    }

    Weight product = 1;
    while (product <= constraint.bound) {
        Weight max_coeff = 0;
        for (Weight q : reduced) {
            max_coeff = std::max(max_coeff, q);
        }

        int best_lambda = 0;
        std::size_t best_count = 0;
        if (max_coeff >= 2) {
            for (Weight candidate = 2; candidate <= max_coeff; ++candidate) {
                std::size_t divisible = 0;
                for (Weight q : reduced) {
                    if (q % candidate == 0) {
                        ++divisible;
                    }
                }
                if (divisible > best_count || (divisible == best_count && static_cast<int>(candidate) > best_lambda)) {
                    best_count = divisible;
                    best_lambda = static_cast<int>(candidate);
                }
            }
        }

        if (best_lambda <= 1) {
            best_lambda = 2;
        }
        base.push_back(best_lambda);

        const Weight lambda_w = static_cast<Weight>(best_lambda);
        if (product > std::numeric_limits<Weight>::max() / lambda_w) {
            break;
        }
        product *= lambda_w;

        for (Weight& q : reduced) {
            q /= lambda_w;
        }
    }

    return base;
}

int make_true_var(CnfFormula& cnf, VariableManager& vm) {
    const int lit = vm.new_var();
    cnf.add_clause({lit});
    return lit;
}

int get_lit(const DigitList& list, int idx) {
    auto it = list.lit_by_index.find(idx);
    if (it == list.lit_by_index.end()) {
        return 0;
    }
    return it->second;
}

void ensure_sorted_unique(DigitList& list) {
    std::sort(list.indices.begin(), list.indices.end());
    list.indices.erase(std::unique(list.indices.begin(), list.indices.end()), list.indices.end());
}

Node* make_leaf(std::vector<std::unique_ptr<Node>>& storage,
                const std::vector<int>& group,
                const std::unordered_map<int, Weight>& weight_by_lit,
                const std::vector<int>& base,
                CnfFormula& cnf,
                VariableManager& vm,
                int true_lit) {
    const std::size_t beta = base.size();
    auto node = std::make_unique<Node>();
    node->leaf = true;
    node->digits.resize(beta + 1);
    for (std::size_t h = 0; h <= beta; ++h) {
        node->digits[h].indices.push_back(0);
        node->digits[h].lit_by_index.emplace(0, true_lit);
    }

    std::vector<std::vector<int>> group_digits;
    group_digits.reserve(group.size());
    for (int lit : group) {
        const auto it = weight_by_lit.find(lit);
        if (it == weight_by_lit.end()) {
            throw std::invalid_argument("structuredpb: literal missing weight in gmto");
        }
        group_digits.push_back(weight_digits(it->second, base));
    }

    for (std::size_t h = 0; h <= beta; ++h) {
        int max_digit = 0;
        for (const auto& dvec : group_digits) {
            max_digit = std::max(max_digit, dvec[h]);
        }
        for (int sigma = 1; sigma <= max_digit; ++sigma) {
            std::vector<int> lits;
            lits.reserve(group.size());
            for (std::size_t gi = 0; gi < group.size(); ++gi) {
                if (group_digits[gi][h] >= sigma) {
                    lits.push_back(group[gi]);
                }
            }
            if (lits.empty()) {
                continue;
            }
            int out_lit = 0;
            if (lits.size() == 1) {
                out_lit = lits[0];
            } else {
                out_lit = vm.new_var();
                for (int src : lits) {
                    cnf.add_clause({-src, out_lit});
                }
            }
            node->digits[h].indices.push_back(sigma);
            node->digits[h].lit_by_index.emplace(sigma, out_lit);
        }
        ensure_sorted_unique(node->digits[h]);
    }

    storage.push_back(std::move(node));
    return storage.back().get();
}

Node* make_parent(std::vector<std::unique_ptr<Node>>& storage,
                  Node* left,
                  Node* right,
                  const std::vector<int>& base,
                  CnfFormula& cnf,
                  VariableManager& vm,
                  int true_lit) {
    const std::size_t beta = base.size();
    auto node = std::make_unique<Node>();
    node->left = left;
    node->right = right;
    node->digits.resize(beta + 1);
    node->carries.assign(beta, 0);

    for (std::size_t h = 0; h <= beta; ++h) {
        node->digits[h].indices.push_back(0);
        node->digits[h].lit_by_index.emplace(0, true_lit);
    }

    for (std::size_t h = 0; h < beta; ++h) {
        const int lambda = base[h];
        const bool has_carry_in = (h > 0 && node->carries[h - 1] != 0);

        bool need_carry = false;
        for (int i : left->digits[h].indices) {
            for (int j : right->digits[h].indices) {
                if (i + j >= lambda || (has_carry_in && i + j + 1 >= lambda)) {
                    need_carry = true;
                    break;
                }
            }
            if (need_carry) {
                break;
            }
        }
        if (need_carry) {
            node->carries[h] = vm.new_var();
        }

        std::unordered_set<int> needed;
        needed.insert(0);
        for (int i : left->digits[h].indices) {
            for (int j : right->digits[h].indices) {
                const int s = i + j;
                if (s < lambda) {
                    needed.insert(s);
                }
                if (s > lambda) {
                    needed.insert(s % lambda);
                }
                if (has_carry_in) {
                    const int s1 = s + 1;
                    if (s1 < lambda) {
                        needed.insert(s1);
                    }
                    if (s1 > lambda) {
                        needed.insert(s1 % lambda);
                    }
                }
            }
        }

        int max_idx = 0;
        for (int idx : needed) {
            max_idx = std::max(max_idx, idx);
        }
        max_idx = std::min(max_idx, lambda - 1);
        for (int idx = 1; idx <= max_idx; ++idx) {
            if (idx == 0) {
                continue;
            }
            const int lit = vm.new_var();
            node->digits[h].indices.push_back(idx);
            node->digits[h].lit_by_index.emplace(idx, lit);
        }
        ensure_sorted_unique(node->digits[h]);
    }

    {
        std::unordered_set<int> needed;
        needed.insert(0);
        const bool has_carry_in = (beta > 0 && node->carries[beta - 1] != 0);
        for (int i : left->digits[beta].indices) {
            for (int j : right->digits[beta].indices) {
                needed.insert(i + j);
                if (has_carry_in) {
                    needed.insert(i + j + 1);
                }
            }
        }
        int max_idx = 0;
        for (int idx : needed) {
            max_idx = std::max(max_idx, idx);
        }
        for (int idx = 1; idx <= max_idx; ++idx) {
            if (idx == 0) {
                continue;
            }
            const int lit = vm.new_var();
            node->digits[beta].indices.push_back(idx);
            node->digits[beta].lit_by_index.emplace(idx, lit);
        }
        ensure_sorted_unique(node->digits[beta]);
    }

    for (std::size_t h = 0; h < beta; ++h) {
        const int lambda = base[h];
        const int carry = node->carries[h];
        const bool has_carry_in = (h > 0 && node->carries[h - 1] != 0);
        const int carry_in = has_carry_in ? node->carries[h - 1] : 0;

        for (int i : left->digits[h].indices) {
            const int li = get_lit(left->digits[h], i);
            for (int j : right->digits[h].indices) {
                const int rj = get_lit(right->digits[h], j);
                const int s = i + j;

                if (s < lambda) {
                    const int out = get_lit(node->digits[h], s);
                    if (out != 0) {
                        Clause cl{-li, -rj, out};
                        if (carry != 0) {
                            cl.push_back(carry);
                        }
                        cnf.add_clause(std::move(cl));
                    }
                }

                if (s >= lambda && carry != 0) {
                    cnf.add_clause({-li, -rj, carry});
                }

                if (s > lambda) {
                    const int out = get_lit(node->digits[h], s % lambda);
                    if (out != 0) {
                        cnf.add_clause({-li, -rj, out});
                    }
                }

                if (!has_carry_in) {
                    continue;
                }

                const int s1 = s + 1;
                if (s1 < lambda) {
                    const int out = get_lit(node->digits[h], s1);
                    if (out != 0) {
                        Clause cl{-carry_in, -li, -rj, out};
                        if (carry != 0) {
                            cl.push_back(carry);
                        }
                        cnf.add_clause(std::move(cl));
                    }
                }

                if (s1 >= lambda && carry != 0) {
                    cnf.add_clause({-carry_in, -li, -rj, carry});
                }

                if (s1 > lambda) {
                    const int out = get_lit(node->digits[h], s1 % lambda);
                    if (out != 0) {
                        cnf.add_clause({-carry_in, -li, -rj, out});
                    }
                }
            }
        }
    }

    {
        const bool has_carry_in = (beta > 0 && node->carries[beta - 1] != 0);
        const int carry_in = has_carry_in ? node->carries[beta - 1] : 0;

        for (int i : left->digits[beta].indices) {
            const int li = get_lit(left->digits[beta], i);
            for (int j : right->digits[beta].indices) {
                const int rj = get_lit(right->digits[beta], j);
                const int s = i + j;

                const int out = get_lit(node->digits[beta], s);
                if (out != 0) {
                    cnf.add_clause({-li, -rj, out});
                }

                if (has_carry_in) {
                    const int out1 = get_lit(node->digits[beta], s + 1);
                    if (out1 != 0) {
                        cnf.add_clause({-carry_in, -li, -rj, out1});
                    }
                }
            }
        }
    }

    storage.push_back(std::move(node));
    return storage.back().get();
}

Node* build_balanced_tree(std::vector<Node*> leaves,
                          std::vector<std::unique_ptr<Node>>& storage,
                          const std::vector<int>& base,
                          CnfFormula& cnf,
                          VariableManager& vm,
                          int true_lit) {
    if (leaves.empty()) {
        return nullptr;
    }
    while (leaves.size() > 1) {
        std::vector<Node*> next;
        next.reserve((leaves.size() + 1) / 2);
        for (std::size_t i = 0; i < leaves.size(); i += 2) {
            if (i + 1 == leaves.size()) {
                next.push_back(leaves[i]);
            } else {
                next.push_back(make_parent(storage, leaves[i], leaves[i + 1], base, cnf, vm, true_lit));
            }
        }
        leaves = std::move(next);
    }
    return leaves.front();
}

void add_comparator(Node* root,
                    const std::vector<int>& base,
                    Weight bound,
                    CnfFormula& cnf) {
    if (root == nullptr) {
        return;
    }

    if (bound == std::numeric_limits<Weight>::max()) {
        return;
    }

    const Weight strict_k = bound + static_cast<Weight>(1);
    const auto kdigits = weight_digits(strict_k, base);
    const std::size_t beta = base.size();

    auto add_for_digit = [&](std::size_t h, int threshold, const std::vector<int>& prefix, bool include_threshold) {
        for (int idx : root->digits[h].indices) {
            const bool beyond = include_threshold ? (idx >= threshold) : (idx > threshold);
            if (!beyond) {
                continue;
            }
            const int lit = get_lit(root->digits[h], idx);
            if (lit == 0) {
                continue;
            }
            Clause cl;
            cl.reserve(prefix.size() + 1);
            for (int guard : prefix) {
                cl.push_back(guard);
            }
            cl.push_back(-lit);
            cnf.add_clause(std::move(cl));
        }
    };

    if (beta == 0) {
        add_for_digit(0, kdigits[0], {}, true);
        return;
    }

    std::vector<int> prefix;
    add_for_digit(beta, kdigits[beta], prefix, false);

    if (kdigits[beta] > 0) {
        const int eq_lit = get_lit(root->digits[beta], kdigits[beta]);
        if (eq_lit == 0) {
            return;
        }
        prefix.push_back(-eq_lit);
    }

    for (std::size_t h = beta; h-- > 1;) {
        add_for_digit(h, kdigits[h], prefix, false);
        if (kdigits[h] > 0) {
            const int eq_lit = get_lit(root->digits[h], kdigits[h]);
            if (eq_lit == 0) {
                return;
            }
            prefix.push_back(-eq_lit);
        }
    }

    add_for_digit(0, kdigits[0], prefix, true);
}

}  // namespace

EncodeResult GmtoEncoder::encode(const GroupedLeqConstraint& constraint,
                                 const EncodeOptions& options) const {
    constraint.validate();

    EncodeResult result;
    VariableManager vm(options.top_id);
    result.cnf.num_vars = options.top_id;

    add_pairwise_amo(constraint, result.cnf);
    const auto weight_by_lit = make_weight_map(constraint);
    const auto groups = preprocess_groups(constraint, weight_by_lit, result.cnf);

    if (groups.empty()) {
        result.cnf.num_vars = std::max(result.cnf.num_vars, vm.max_var());
        result.stats.auxiliary_variables = static_cast<std::size_t>(result.cnf.num_vars - options.top_id);
        result.stats.clauses = result.cnf.clauses.size();
        return result;
    }

    if (grouped_capacity(groups, weight_by_lit) <= constraint.bound) {
        result.cnf.num_vars = std::max(result.cnf.num_vars, vm.max_var());
        result.stats.auxiliary_variables = static_cast<std::size_t>(result.cnf.num_vars - options.top_id);
        result.stats.clauses = result.cnf.clauses.size();
        return result;
    }

    const auto base = select_base_greedy(constraint);

    const int true_lit = make_true_var(result.cnf, vm);

    std::vector<std::unique_ptr<Node>> storage;
    storage.reserve(groups.size() * 2 + 1);

    std::vector<Node*> leaves;
    leaves.reserve(groups.size());
    for (const auto& group : groups) {
        leaves.push_back(make_leaf(storage, group, weight_by_lit, base, result.cnf, vm, true_lit));
    }

    Node* root = build_balanced_tree(leaves, storage, base, result.cnf, vm, true_lit);
    add_comparator(root, base, constraint.bound, result.cnf);

    result.cnf.num_vars = std::max(result.cnf.num_vars, vm.max_var());
    result.stats.auxiliary_variables = static_cast<std::size_t>(result.cnf.num_vars - options.top_id);
    result.stats.clauses = result.cnf.clauses.size();
    return result;
}

}  // namespace structuredpb
