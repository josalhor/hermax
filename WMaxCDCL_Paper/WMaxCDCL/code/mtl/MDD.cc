//
// Created by jordi on 24/6/21.
//

#include "mtl/MDD.h"

using namespace Minisat;

MDD * MDD::mddtrue=NULL;
MDD * MDD::mddfalse=NULL;

MDD * MDD::MDDFalse(){
    if(mddfalse==NULL)
     mddfalse = new MDD(false);
    return mddfalse;
}
 MDD * MDD::MDDTrue(){
    if(mddtrue==NULL)
      mddtrue = new MDD(true);
    return mddtrue;
}

MDDBuilder::MDDBuilder(vec2<int,vec<int64_t> > &Q, int64_t K):
Q(Q),K(K)
{
    id=2;
    //for(int i = 0; i < Q.size(); i++) {
    //    //The literals of each group are decreasingly ordered by coefficient
    //    sortCoefsDecreasing(Q[i], X[i]);
    //}
    initL();
}

MDDBuilder::~MDDBuilder(){
    for(int i = 0; i < all_MDDs.size(); i++)
        delete all_MDDs[i];
}

void MDDBuilder::initL() {
    int depth = Q.size()+1;
    vec<int64_t> sums_max(depth);
    L.init(depth-1);
    R_MDD rm, rm_false;

    sums_max[depth-1] = 0; // for the leaves
    for(int i=depth-2;i>= 0;i--)
        sums_max[i] = sums_max[i+1] + (int64_t) max(Q[i]);

    rm_false=R_MDD(MDD::MDDFalse(),INT64_MIN,-1);

    for(int i=0;i<depth-1;i++) {
        L[i].push(rm_false); //Skip bottom node
        L[i].push(R_MDD(MDD::MDDTrue(),sums_max[i],INT64_MAX));
    }

    L[depth-1].push(rm_false); //Skip bottom node
    L[depth-1].push(R_MDD(MDD::MDDTrue(),0,INT64_MAX));
}

MDD * MDDBuilder::getMDD(){
    return getMDD(0,K).mdd;
}

//Insert ordered with respect to the intervals [B,Y].
// Precondition: rm_in doesn't exists in layer
void MDDBuilder::insertMDD(R_MDD rm_in,int i_l) {

    vec<R_MDD> & layer=L[i_l];
    layer.push();
    int i = layer.size()-1;

    while(i>0 && rm_in.Y < layer[i-1].B){
    	layer[i]=layer[i-1];
    	--i;
    }
    layer[i]=rm_in;

}

//Binary search
R_MDD MDDBuilder::searchMDD(int i_l, int64_t i_k) {
    vec<R_MDD> & layer = L[i_l];

    R_MDD res,act;
    res.mdd = NULL;
    int n=layer.size();
    int i=0,min=0,max=0;
    bool found=false;

    if(n>0) {
        max=n-1;
        i=(max-min)/2;
        while(min<=max && !found) {
            act=layer[i];
            if(i_k>=act.B && i_k<=act.Y) {
                res=act;
                found=true;
            } else if(act.B>i_k){
                max=i-1;
            } else { //if(act.Y<i_k) { //otherwise
                min=i+1;
            }
            i=min+(max-min)/2;
        }
    }
    return res;
}

R_MDD MDDBuilder::getMDD(int i_l, int64_t i_k) {
    R_MDD rm_new;
    MDD *mdd_new=NULL;

    rm_new=searchMDD(i_l,i_k);
    assert(i_l < Q.size() || rm_new.mdd!=NULL);

    if(rm_new.mdd==NULL){
        vec<MDD *> mdds;
        int64_t maxB = INT64_MIN;
        int64_t minY = INT64_MAX;
        bool allequal = true;
        MDD * m = NULL;

        for(int i = 0; i < Q[i_l].size(); i++){
            R_MDD rm = getMDD(i_l+1,i_k-Q[i_l][i]);
            mdds.push(rm.mdd);
            if(m==NULL)
                m = rm.mdd;
            else
                allequal = allequal && m==rm.mdd;

            if(maxB < inf_sum(rm.B,Q[i_l][i])) maxB = inf_sum(rm.B,Q[i_l][i]);
            if(inf_sum(rm.Y,Q[i_l][i]) <  minY) minY = inf_sum(rm.Y,Q[i_l][i]);
        }

        //Else case, same as coefficient 0
        R_MDD rm = getMDD(i_l+1,i_k);
        mdds.push(rm.mdd);
        allequal = allequal && m==rm.mdd;

        if(maxB < rm.B) maxB = rm.B;
        if(rm.Y < minY) minY = rm.Y;


        if(allequal) //Reuse unique child
            rm_new=R_MDD(mdds[0],maxB,rm.Y);
        else {
            mdd_new=new MDD(i_l,id++);
            for(int i = 0; i < mdds.size()-1; i++)
                mdd_new->children.push(mdds[i]);
            mdd_new->elsechild=mdds[mdds.size()-1];
            rm_new=R_MDD(mdd_new,maxB,minY);

            insertMDD(rm_new,i_l);
            all_MDDs.push(mdd_new);
        }
    }
    assert(rm_new.mdd!=NULL);
    return rm_new;
}




