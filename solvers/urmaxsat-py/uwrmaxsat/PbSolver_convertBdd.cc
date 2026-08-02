/**************************************************************************[PbSolver_convertBdd.cc]
Copyright (c) 2005-2010, Niklas Een, Niklas Sorensson

KP-MiniSat+ based on MiniSat+ -- Copyright (c) 2018-2020 Michał Karpiński, Marek Piotrów

UWrMaxSat based on KP-MiniSat+ -- Copyright (c) 2019-2020 Marek Piotrów

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

#include "PbSolver.h"
#include "FEnv.h"
#include "Debug.h"


//=================================================================================================

#define lit2fml(p) id(var(var(p)),sign(p))

static
Formula convertOneToBdd(const vec<Lit>& ps, const vec<Int>& Cs, Int lo, int max_cost)
{
    FEnv::push();

    int size = Cs.size(), last;
    vec<Int>   material_left(size+1);
    vec<Pair<Interval<Int>, Formula> >     ttf(size+1);
    vec<std::map<Interval<Int>, Formula> > memo(size+1);
    Pair<Interval<Int>, Formula> tt, ff, result;
    const Int zero = 0; Int sum = 0;

    for (int i = 0; i < ttf.size(); i++) ttf[i].snd = _undef_;
    material_left[0] = 0;
    for (int i = 1; i < material_left.size(); i++)  material_left[i] = material_left[i-1] +  Cs[i-1];
    last = size;
    do {
        // lo - sum[last] <= (Cs[0]*ps[0] + ... + Cs[last-1]*ps[last-1])
        Int lower_limit = lo - sum;

        if (FEnv::topSize() > max_cost) {
            FEnv::pop();
            return _undef_;
        }
        if (lower_limit <= 0)
            result = Pair_new( Interval_new(Int_MIN,zero), _1_);
        else if (lower_limit > material_left[last])
            result = Pair_new( Interval_new(material_left[last] + 1, Int_MAX), _0_);
        else {
            assert(last > 0);
            auto search = memo[last].find(Interval_new(lower_limit,lower_limit));
    
            if (search == memo[last].end()) {
                sum += Cs[--last];
                continue;                                         // continue with computing the tt child node
             } else result = Pair_new(search->first, search->second);
        }
        do {
            if (ttf[last].snd == _undef_) {
               ttf[last] = result;
               sum -= Cs[last];
               break;                                             // continue with computing the ff child node
            }
            tt = ttf[last]; ff = result; ttf[last].snd = _undef_; // both children (tt and ff) are available with their intervals

            Int tt_beta = tt.fst.fst, tt_gamma = tt.fst.snd;      // [beta, gamma] is a corresponding interval
            Int ff_beta = ff.fst.fst, ff_gamma = ff.fst.snd;

            Interval<Int> interval = Interval_new(max(tt_beta.add(Cs[last]),ff_beta), min(tt_gamma.add(Cs[last]),ff_gamma));
            Formula fm = (tt.snd == ff.snd ? tt.snd : ITE(lit2fml(ps[last]), tt.snd, ff.snd));

            memo[++last][interval] = fm;                          // continue with the parent node
            result = Pair_new(interval, fm);
        } while (last < size);
    } while (last < size);
    if (opt_verbosity >= 1 && opt_minimization != 1 || opt_verbosity >= 2)
        if (FEnv::topSize() > 0)
            /**/ reportf("BDD-cost:%5d\n", FEnv::topSize());
        else if (!opt_maxsat) reportf("\n");

    FEnv::keep();
    return result.snd;
}

Formula convertToBdd(const Linear& c, int max_cost)
{
    vec<Lit> ls;
    vec<Int> Cs;
    Int csum = 0;
    Formula ret;

    for (int j = 0; j < c.size; j++)
        ls.push(c[j]), Cs.push(c(j)), csum += c(j);

    ret = convertOneToBdd(ls, Cs, c.lo, max_cost);    
    if(ret == _undef_ ) return ret;

    if(c.hi != Int_MAX) {
      ls.clear(); Cs.clear();
      for(int i=0; i<c.size; i++)
        ls.push(~c[i]), Cs.push(c(i));
      ret &= convertOneToBdd(ls, Cs, csum - c.hi, max_cost);
    }
    extern PbSolver *pb_solver;
    return ret == _undef_ || c.lit == lit_Undef || pb_solver->use_base_assump ? ret : ~lit2fml(c.lit) | ret ;
}
