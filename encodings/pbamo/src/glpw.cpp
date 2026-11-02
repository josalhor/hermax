#include "structuredpb/glpw.hpp"

#include "amo.hpp"

#include <algorithm>
#include <cstdint>
#include <memory>
#include <map>
#include <unordered_map>
#include <utility>
#include <vector>

namespace structuredpb {
namespace {

// A handle is either an original signed literal or a positive virtual node
// above base_. Virtual nodes acquire real DIMACS IDs only when demanded.
// This preserves shared subcircuits without emitting unused totalizer outputs.
class SharedWatchdogs {
public:
    using Handle = std::int64_t;
    using List = std::vector<Handle>;

    SharedWatchdogs(VariableManager& variables, CnfFormula& cnf)
        : variables_(variables), cnf_(cnf), base_(variables.max_var()) {}

    Handle group_bit(List sources) {
        if (sources.empty()) return 0;
        if (sources.size() == 1) return sources.front();
        std::sort(sources.begin(), sources.end());
        const auto it = group_bits_.find(sources);
        if (it != group_bits_.end()) return it->second;
        Node node;
        node.sources = sources;
        const Handle output = add_node(std::move(node));
        group_bits_.emplace(std::move(sources), output);
        return output;
    }

    List merge(const List& lhs, const List& rhs) {
        if (lhs.empty()) return rhs;
        if (rhs.empty()) return lhs;
        auto key = lhs < rhs ? std::make_pair(lhs, rhs) : std::make_pair(rhs, lhs);
        const auto found = mergers_.find(key);
        if (found != mergers_.end()) return found->second;
        auto inputs = std::make_shared<Merge>(Merge{lhs, rhs});
        List output;
        output.reserve(lhs.size() + rhs.size());
        for (std::size_t i = 0; i < lhs.size() + rhs.size(); ++i) {
            Node node;
            node.merge = inputs;
            node.index = i;
            output.push_back(add_node(std::move(node)));
        }
        mergers_.emplace(std::move(key), output);
        return output;
    }

    List bucket(const List& leaves, std::size_t begin, std::size_t end,
                std::size_t excluded) {
        if (end - begin == 1) {
            return begin == excluded || leaves[begin] == 0
                ? List{} : List{leaves[begin]};
        }
        const auto middle = begin + (end - begin) / 2;
        // Explicit order makes auxiliary IDs and clause order reproducible.
        auto left = bucket(leaves, begin, middle, excluded);
        auto right = bucket(leaves, middle, end, excluded);
        return merge(left, right);
    }

    int materialize(Handle handle) {
        if (handle <= base_) return static_cast<int>(handle);
        const auto index = static_cast<std::size_t>(handle - base_ - 1);
        if (nodes_[index].literal != 0) return nodes_[index].literal;
        // Copy graph references before recursion: materialization adds clauses,
        // but it does not create graph nodes.
        const int out = variables_.new_var();
        nodes_[index].literal = out;
        const auto merge_node = nodes_[index].merge;
        if (!merge_node) {
            for (Handle input : nodes_[index].sources)
                cnf_.add_clause({-materialize(input), out});
            return out;
        }
        const auto k = nodes_[index].index;
        const auto& left = merge_node->left;
        const auto& right = merge_node->right;
        if (k < left.size()) cnf_.add_clause({-materialize(left[k]), out});
        if (k < right.size()) cnf_.add_clause({-materialize(right[k]), out});
        // Only pairs whose counts imply this exact output are needed.
        const std::size_t first = k > right.size() ? k - right.size() : 0;
        for (std::size_t i = first; i < left.size() && i < k; ++i) {
            const std::size_t j = k - i - 1;
            if (j < right.size())
                cnf_.add_clause({-materialize(left[i]), -materialize(right[j]), out});
        }
        return out;
    }

private:
    struct Merge { List left, right; };
    struct Node {
        List sources;
        std::shared_ptr<const Merge> merge;
        std::size_t index = 0;
        int literal = 0;
    };

    Handle add_node(Node node) {
        nodes_.push_back(std::move(node));
        return static_cast<Handle>(base_) + static_cast<Handle>(nodes_.size());
    }

    VariableManager& variables_;
    CnfFormula& cnf_;
    const int base_;
    std::vector<Node> nodes_;
    std::map<List, Handle> group_bits_;
    std::map<std::pair<List, List>, List> mergers_;
};

}  // namespace

EncodeResult GlpwEncoder::encode(const GroupedLeqConstraint& constraint,
                                 const EncodeOptions& options) const {
    constraint.validate();
    const int top_id = constraint.effective_top_id(options.top_id);
    EncodeResult result(options.clause_memory);
    result.cnf.num_vars = top_id;
    VariableManager variables(top_id);
    add_amo_groups(constraint, result.cnf, variables);

    std::unordered_map<int, Weight> weights;
    for (const auto& term : constraint.terms) weights.emplace(term.lit, term.weight);
    std::vector<std::vector<WeightedLiteral>> groups(constraint.groups.size());
    std::vector<Weight> maxima(groups.size(), 0);
    Weight qmax = 0;
    for (std::size_t i = 0; i < groups.size(); ++i) {
        for (int lit : constraint.groups[i]) {
            const Weight weight = weights.at(lit);
            if (weight > constraint.bound) {
                result.cnf.add_clause({-lit});
            } else {
                groups[i].push_back({lit, weight});
                maxima[i] = std::max(maxima[i], weight);
                qmax = std::max(qmax, weight);
            }
        }
    }

    if (qmax != 0) {
        std::size_t p = 0;
        for (Weight q = qmax; q > 1; q >>= 1U) ++p;
        const Weight scale = Weight{1} << p;
        SharedWatchdogs shared(variables, result.cnf);
        std::vector<SharedWatchdogs::List> bits(p + 1, SharedWatchdogs::List(groups.size(), 0));
        bool bits_ready = false;
        auto prepare_bits = [&]() {
            if (bits_ready) return;
            for (std::size_t r = 0; r <= p; ++r) {
                for (std::size_t i = 0; i < groups.size(); ++i) {
                    SharedWatchdogs::List sources;
                    for (const auto& term : groups[i])
                        if ((term.weight >> r) & Weight{1}) sources.push_back(term.lit);
                    bits[r][i] = shared.group_bit(std::move(sources));
                }
            }
            bits_ready = true;
        };

        for (std::size_t excluded = 0; excluded < groups.size(); ++excluded) {
            // One phi totalizer per bit and excluded group, shared by all
            // local watchdogs for literals in the same group.
            std::vector<SharedWatchdogs::List> buckets(p + 1);
            bool buckets_ready = false;
            for (const auto& term : groups[excluded]) {
                const Weight remaining = constraint.bound - term.weight;
                // If all other groups fit, this local implication is tautological.
                Weight capacity = 0;
                bool can_overflow = false;
                for (std::size_t j = 0; j < groups.size(); ++j) {
                    if (j == excluded) continue;
                    if (maxima[j] > remaining - capacity) {
                        can_overflow = true;
                        break;
                    }
                    capacity += maxima[j];
                }
                if (!can_overflow) continue;
                if (!buckets_ready) {
                    prepare_bits();
                    for (std::size_t r = 0; r <= p; ++r)
                        buckets[r] = shared.bucket(bits[r], 0, groups.size(), excluded);
                    buckets_ready = true;
                }

                // ceil((remaining + 1) / scale), without overflowing at
                // UINT64_MAX. Padding is scale - 1 - (remaining % scale).
                const Weight quotient = remaining / scale;
                const Weight padding = scale - 1 - (remaining % scale);
                SharedWatchdogs::List sum;
                for (std::size_t r = 0; r <= p; ++r) {
                    SharedWatchdogs::List carries;
                    for (std::size_t j = 1; j < sum.size(); j += 2)
                        carries.push_back(sum[j]);
                    sum = shared.merge(buckets[r], carries);
                    // A leading zero denotes a constant true threshold. Moving
                    // padding here shares phi and psi regardless of this bit.
                    if ((padding >> r) & Weight{1}) sum.insert(sum.begin(), 0);
                }
                // m = quotient + 1; compare before converting or incrementing.
                if (quotient < sum.size()) {
                    const auto overflow = sum[static_cast<std::size_t>(quotient)];
                    if (overflow == 0) result.cnf.add_clause({-term.lit});
                    else result.cnf.add_clause({-term.lit, -shared.materialize(overflow)});
                }
            }
        }
    }
    result.cnf.num_vars = std::max(result.cnf.num_vars, variables.max_var());
    result.stats.auxiliary_variables = static_cast<std::size_t>(result.cnf.num_vars - top_id);
    result.stats.clauses = result.cnf.clauses.size();
    return result;
}

}  // namespace structuredpb
