//
// Created by jordi on 24/6/21.
//

#include "core/SolverTypes.h"

#ifndef VEC2_H
#define VEC2_H

using namespace Minisat;

template<class Idx, class Vec>
class vec2
{
    vec<Vec>  occs;

public:
    void  init      (const Idx& idx){ occs.growTo(toInt(idx)+1);}
    Vec&  operator[](const Idx& idx){ return occs[toInt(idx)]; }
    int size() {return occs.size();}
    void     shrink_  (int nelems) {occs.shrink_(nelems);}

    void  clear(bool free = false){
        occs   .clear(free);
    }
};


#endif //VEC2_H
