#ifndef HERMAX_PACKED_CLAUSES_HPP
#define HERMAX_PACKED_CLAUSES_HPP

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <new>
#include <stdexcept>
#include <type_traits>
#include <vector>

namespace hermax::clauses {

struct Memory {
    void *(*allocate)(size_t) = std::malloc;
    void (*deallocate)(void *) = std::free;
};

template <typename T> struct Allocator {
    using value_type = T;
    using propagate_on_container_move_assignment = std::true_type;
    Memory memory;
    Allocator() = default;
    explicit Allocator(Memory memory) : memory(memory) {}
    template <typename U> Allocator(const Allocator<U> &other) : memory(other.memory) {}
    T *allocate(size_t count) {
        if (count > SIZE_MAX / sizeof(T)) throw std::bad_alloc();
        void *result = memory.allocate(count * sizeof(T));
        if (!result) throw std::bad_alloc();
        return static_cast<T *>(result);
    }
    void deallocate(T *value, size_t) { memory.deallocate(value); }
    template <typename U> bool operator==(const Allocator<U> &other) const {
        return memory.allocate == other.memory.allocate && memory.deallocate == other.memory.deallocate;
    }
    template <typename U> bool operator!=(const Allocator<U> &other) const { return !(*this == other); }
};

class PackedClauses {
public:
    std::vector<int32_t, Allocator<int32_t>> literals;
    std::vector<size_t, Allocator<size_t>> ends;

    explicit PackedClauses(Memory memory = {})
        : literals(Allocator<int32_t>(memory)), ends(Allocator<size_t>(memory)) { ends.push_back(0); }
    size_t size() const { return ends.empty() ? 0 : ends.size() - 1; }

    void append(const int32_t *values, size_t count) {
        for (size_t i = 0; i < count; ++i) {
            if (!values[i] || values[i] == std::numeric_limits<int32_t>::min())
                throw std::invalid_argument("Invalid native DIMACS literal.");
        }
        if (ends.empty()) ends.push_back(0);
        size_t previous = literals.size();
        try {
            if (count) literals.insert(literals.end(), values, values + count);
            ends.push_back(literals.size());
        } catch (...) { literals.resize(previous); throw; }
    }

    void push_back(const std::vector<int32_t> &row) { append(row.data(), row.size()); }

    struct Row {
        const int32_t *values;
        size_t count;
        size_t size() const { return count; }
        const int32_t *begin() const { return values; }
        const int32_t *end() const { return count ? values + count : values; }
        int32_t operator[](size_t index) const { return values[index]; }
    };
    Row operator[](size_t index) const {
        size_t first = ends[index], count = ends[index + 1] - first;
        return Row{count ? literals.data() + first : nullptr, count};
    }
};

} // namespace hermax::clauses
#endif
