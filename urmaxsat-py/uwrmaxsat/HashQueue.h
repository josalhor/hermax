/*****************************************************************************[Hardware_sorters.cc]
Copyright (c) 2017-2018, Marek Piotrów, Michał Karpiński

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT
OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
**************************************************************************************************/

#ifndef HashQueue_h
#define HashQueue_h

#include <climits>
#include "Global.h"
#include "minisat/mtl/Vec.h"
#include "Map.h"
#include "Heap.h"

static const int prime[] = { 2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47 };
static const int primeIndex[] = {0, 0, 1, 2, 0, 3, 0, 4, 0, 0, 0, 5, 0, 6, 0, 0, 0, 7, 0, 8,
                                 0, 0, 0, 9, 0, 0, 0, 0, 0,10, 0,11, 0, 0, 0, 0, 0,12, 0, 0, 0,13, 0,14, 0, 0, 0,15 };

constexpr size_t log2(size_t n) { return ( (n<2) ? 1 : 1+log2(n/2)); }
constexpr size_t pbits = log2(elemsof(prime)), pmask = (1 << pbits) - 1;

//static bool cmp(int left, int right);

class HashQueue {
    struct BaseData {
        unsigned long long int base0, base1;
        int cost;
        int carry_ins;
        int index;
    } ;
    struct Comp {
        vec<BaseData * > *mapptr;
        bool operator()(int i, int j) { return (*mapptr)[i]->cost < (*mapptr)[j]->cost ; }
        Comp(vec<BaseData * > *ptr) : mapptr(ptr) { }
    } ;
    Map<unsigned long long int, BaseData> baseMap;
    vec<BaseData * > mapPtr;
    int lastFree;
    Comp mycmp;
    Heap<Comp> queue;
    static const BaseData nullBase;
    void unpackBase(unsigned long long int base0, unsigned long long int base1, vec<int>& nbase) {
        nbase.clear(); 
        while (base0 & pmask) { nbase.push(prime[(base0 & pmask) - 1]); base0 >>= pbits; }
        while (base1 & pmask) { nbase.push(prime[(base1 & pmask) - 1]); base1 >>= pbits; }
    }
    void packBase(const vec<int>& nbase, unsigned long long int &base0, unsigned long long int &base1) {
        base0 = base1 = 0;
        for (int sz = maxBaseSize/2, i = nbase.size() - 1; i >= 0; i--) 
           i < sz ? base0 = (base0 << pbits) | primeIndex[nbase[i]] 
                  : base1 = (base1 << pbits) | primeIndex[nbase[i]];
    }
    unsigned long long int hashBase(const vec<int>& nbase) {
        int count[elemsof(prime)] = {0};
        unsigned long long int  hash = 0;
        for (int i = 0; i < nbase.size(); i++) 
            count[primeIndex[nbase[i]]-1]++;
        for (int i = (int)elemsof(prime) - 1; i >= 0; i--) 
            hash = ((hash << 1) | 1) << count[i];
        return hash;
    }
public:
    HashQueue(int capacity = 1) : baseMap(nullBase, capacity), lastFree(-1), mycmp(&mapPtr), queue(mycmp) { }
    void clear(void) { mapPtr.clear(); }
    static const int maxBaseSize;
    bool isEmpty() { return queue.empty(); }
    int popMin(vec<int> &new_base, int &carry_ins) {
        if (queue.empty()) return INT_MAX;
        int minIndex = queue.getmin();
        BaseData *minPtr = mapPtr[minIndex];
        queue.indices[minIndex] = lastFree;
        lastFree = minIndex;
        minPtr->index = -1;
        unpackBase(minPtr->base0, minPtr->base1, new_base);
        carry_ins = minPtr->carry_ins;
        return minPtr->cost;
    }
    void push(const vec<int>& base, int cost, int carry_ins) {
        unsigned long long int pbase0, pbase1, hash = hashBase(base); 
        packBase(base, pbase0, pbase1);
        BaseData &data = baseMap.ref(hash);
        if (cost < data.cost) {
            data.base0 = pbase0;
            data.base1 = pbase1;
            data.cost  = cost;
            data.carry_ins = carry_ins;
            if (data.index == -1) {
                int new_index;
                if (lastFree != -1) 
                    new_index=lastFree,lastFree=queue.indices[lastFree],mapPtr[new_index] = &data;
                else 
                    new_index=queue.indices.size(), queue.indices.push(0), mapPtr.push(&data);
                queue.insert(new_index);
                data.index = new_index;
            } else 
                queue.increase(data.index);
        }
    }
};

const int HashQueue::maxBaseSize = 2 * sizeof(unsigned long long int) * CHAR_BIT / pbits;

const HashQueue::BaseData HashQueue::nullBase = {0, 0, INT_MAX, 0, -1};
/*vec<HashQueue::BaseData *> HashQueue::mapPtr;

static bool cmp(int left, int right) {
        return HashQueue::mapPtr[left]->cost < HashQueue::mapPtr[right]->cost ; 
}*/

#endif
