//
// Created by jordi on 24/6/21.
//

#ifndef MDD_H
#define MDD_H

#include "mtl/Vec.h"
#include "mtl/Vec2.h"
#include "core/SolverTypes.h"

using namespace Minisat;

struct R_MDD;

class MDD;

class MDDBuilder {

private:
    vec<MDD *> all_MDDs;
    vec2<int,vec<R_MDD> > L;
    int id;
    vec2<int,vec<int64_t> > & Q;
    int K;
    void initL();
    void insertMDD(R_MDD rb_in,int i_l);
    R_MDD searchMDD(int i_l, int64_t i_k);
    R_MDD getMDD(int i_l, int64_t i_k);


    inline int64_t inf_sum(int64_t possible_inf, int64_t x){
        if(possible_inf == INT64_MAX)
            return INT64_MAX;
        else if(possible_inf == INT64_MIN)
            return INT64_MIN;
        else return possible_inf + x;

   }
   inline int64_t max(vec<int64_t> & v){
        int64_t m = 0;
        for(int i = 0; i < v.size(); ++i)
            if(v[i] > m)
                m = v[i];
        return m;
    }

public:

    //Constructor
    MDDBuilder(vec2<int,vec<int64_t> > &Q, int64_t K);
    ~MDDBuilder();

    MDD * getMDD();
};


//Encapsulation of an MDD with its interval [B,Y]
struct R_MDD {
    MDD *mdd;
    int64_t B;
    int64_t Y;
    R_MDD() {
        mdd=NULL;
        B=0;
        Y=0;
    }
    R_MDD(MDD * m, int64_t b, int64_t y) {
        mdd=m;
        B=b;
        Y=y;
    }
};

class MDD {

private:

    static MDD * mddtrue; //True leaf node
    static MDD * mddfalse; //False leaf node

    //Trivial MDD constructor
    MDD(bool b){
        id = b ? 1 : 0;
    }

public:

    //Invariant: the id of the parent is always greater than the id of the children
    int id;
    int layer; //Based on the layer, the selectors are consulted externally
    vec<MDD *> children;
    MDD * elsechild;

    //Constructor
    MDD(int layer, int id){
        this->layer=layer;
        this->id=id;
    };

    //Destructor
    ~MDD(){};

    //Get leaf nodes
    static MDD * MDDTrue();
    static MDD * MDDFalse();

/*
    //Get all the selectors
    const vec<Lit> & getSelectors() const;

    //Get the i-th chile
    MDD * getChildByIdx(int idx) const;

    //Get the else child
    MDD * getElseChild()const;

    //Get number of selectors
    int getNSelectors() const;

    //Check if the MDD is leaf (either true or false)
    bool isLeafMDD() const;

    //Check if the MDD is the true leaf
    bool isTrueMDD() const;

    //Check if the MDD is the false leaf
    bool isFalseMDD() const;
*/

   /* //Add a child to the MDD
    //They must be inserted in order
    void addChild(MDD * child){
        children.push(child);
    };

    //Set the else child of the MDD
    void setElseChild(MDD * child){
        elsechild=child;
    };*/
};



#endif //MDD_H
