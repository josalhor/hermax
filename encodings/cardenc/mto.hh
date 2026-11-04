/*
 * mto.hh (based on the 'card' library from BOLT)
 *
 *  Created on: Sep 25, 2017
 *      Author: aign
 */

#ifndef MTO_HH_
#define MTO_HH_

#include <cmath>
#include <utility>
#include "common.hh"
#include "ptypes.hh"
#include "utils.hh"

// totalizer
//=============================================================================
inline void to_UA(
	int& top_id,
	ClauseSet& clset,
	vector<int>& outlst,
	vector<int>& alst,
	vector<int>& blst
)
{
	size_t m = alst.size();
	size_t n = blst.size();

	// add the constraints
	for (size_t j = 0; j < n; j++)
		clset.create_binary_clause(-blst[j], outlst[j]);

	for (size_t i = 0; i < m; i++)
		clset.create_binary_clause(-alst[i], outlst[i]);

	for (size_t i = 1; i <= m; i++) {
		for (size_t j = 1; j <= n; j++)
			clset.create_ternary_clause(-alst[i - 1], -blst[j - 1], outlst[i + j - 1]);
	}
}

//
//=============================================================================
inline void to_TO(
	int& top_id,
	ClauseSet& clset,
	vector<int>& outvars,
	vector<int>& invars
)
{
	const size_t n = invars.size();
	if (n < 2) {
		outvars = invars;
		return;
	}

	outvars.resize(n);
	for (size_t i = 0; i < n; i++)
		outvars[i] = ++top_id;

	struct Frame {
		vector<int> inputs;
		vector<int> outputs;
	};
	vector<Frame> stack;
	stack.push_back(Frame{invars, outvars});
	while (!stack.empty()) {
		Frame current = std::move(stack.back());
		stack.pop_back();

		const size_t size = current.inputs.size();
		const size_t half = size - (size >> 1);
		vector<int> left(current.inputs.begin(), current.inputs.begin() + half);
		vector<int> right(current.inputs.begin() + half, current.inputs.end());
		vector<int> left_out(half), right_out(size - half);

		if (half < 2) left_out = left;
		else for (int& lit : left_out) lit = ++top_id;
		if (right.size() < 2) right_out = right;
		else for (int& lit : right_out) lit = ++top_id;

		to_UA(top_id, clset, current.outputs, left_out, right_out);
		// Push left first so right is processed first, preserving clause order.
		if (half >= 2) stack.push_back(Frame{std::move(left), std::move(left_out)});
		if (right.size() >= 2) stack.push_back(Frame{std::move(right), std::move(right_out)});
	}
}

//
//=============================================================================
inline void to_encode_atmostN(
	int& top_id,
	ClauseSet& clset,
	vector<int>& vars,
	int k
)
{
	size_t n = vars.size();

	if ((size_t)k >= n)
		return;

	if (k == 0) {
		common_encode_atmost0(clset, vars);
		return;
	}

	vector<int> outvars;
	to_TO(top_id, clset, outvars, vars);
	clset.create_unit_clause(-outvars[k]);
}

//
//=============================================================================
inline void to_encode_atleastN(
	int& top_id,
	ClauseSet& clset,
	vector<int>& vars,
	int tval
)
{
	vector<int> ps;
	int nrhs = -tval;

	for(size_t i = 0; i < vars.size(); i++) {
		nrhs += 1; // The weight in fact
		ps.push_back(-vars[i]);
	}

	to_encode_atmostN(top_id, clset, ps, nrhs);
}

// modulo totalizer
//=============================================================================
inline void mto_MUA_A(
	int& top_id,
	ClauseSet& clset,
	vector<int>& hs,
	vector<int>& rs,
	vector<int>& fs,
	vector<int>& as,
	vector<int>& gs,
	vector<int>& bs,
	size_t p
)
{
	size_t sigma = hs.size();
	size_t alfa  = fs.size();
	size_t m     = as.size();
	size_t beta  = gs.size();
	size_t n     = bs.size();

	int c = ++top_id;

	// phi 1
	// i = 0 (n < p necessarily)
	for (size_t j = 1; j <= n; j++)
		clset.create_ternary_clause(-bs[j - 1], rs[j - 1], c);

	// j = 0 (m < p necessarily)
	for (size_t i = 1; i <= m; i++)
		clset.create_ternary_clause(-as[i - 1], rs[i - 1], c);

	// i, j != 0
	for (size_t i = 1; i <= m; i++) {
		for (size_t j = 1; j <= n; j++) {
			if (i + j < p) {
				vector<int> lits(4);
				lits[0] = -as[i - 1];
				lits[1] = -bs[j - 1];
				lits[2] =  rs[i + j - 1];
				lits[3] = c;
				clset.create_clause(lits);
			}
			else if (i + j > p)
				clset.create_ternary_clause(-as[i - 1], -bs[j - 1], rs[((i + j) % p) - 1]);
			else
				clset.create_ternary_clause(-as[i - 1], -bs[j - 1], c);
		}
	}

	// phi 2
	// i = 0 j = 0
	if (sigma == 0)
		clset.create_unit_clause(-c);
	else
		clset.create_binary_clause(-c, hs[0]);

	// i = 0
	for (size_t j = 1; j <= beta; j++) {
		if (j <= sigma)
			clset.create_binary_clause(-gs[j - 1], hs[j - 1]);
		else
			clset.create_unit_clause  (-gs[j - 1]);

		if (j < sigma)
			clset.create_ternary_clause(-c, -gs[j - 1], hs[j]);
		else
			clset.create_binary_clause (-c, -gs[j - 1]);
	}

	// j = 0
	for (size_t i = 1; i <= alfa; i++) {
		if (i <= sigma)
			clset.create_binary_clause(-fs[i - 1], hs[i - 1]);
		else
			clset.create_unit_clause  (-fs[i - 1]);

		if (i < sigma)
			clset.create_ternary_clause(-c, -fs[i - 1], hs[i]);
		else
			clset.create_binary_clause (-c, -fs[i - 1]);
	}

	// i, j != 0
	for (size_t i = 1; i <= alfa; i++) {
		for (size_t j = 1; j <= beta; j++) {
			if (i + j <= sigma)
				clset.create_ternary_clause(-fs[i - 1], -gs[j - 1], hs[i + j - 1]);
			else
				clset.create_binary_clause (-fs[i - 1], -gs[j - 1]);

			vector<int> lits(3);
			lits[0] = -c;
			lits[1] = -fs[i - 1];
			lits[2] = -gs[j - 1];

			if (i + j < sigma)
				lits.push_back(hs[i + j]);

			clset.create_clause(lits);
		}
	}
}

//
//=============================================================================
inline void mto_MTO_A(
	int& top_id,
	ClauseSet& clset,
	vector<int>& us,
	vector<int>& ls,
	vector<int>& is,
	size_t p,
	int k = -1)
{
	if (is.size() < p) {
		us.clear();
		to_TO(top_id, clset, ls, is);
		return;
	}

	size_t un = is.size() / p;
	if (k >= 0 && k / p < un) un = k / p;
	us.resize(un);
	for (int& lit : us) lit = ++top_id;
	ls.resize(p - 1);
	for (int& lit : ls) lit = ++top_id;

	struct Frame {
		vector<int> inputs;
		vector<int> upper;
		vector<int> lower;
	};
	vector<Frame> stack;
	stack.push_back(Frame{is, us, ls});
	while (!stack.empty()) {
		Frame current = std::move(stack.back());
		stack.pop_back();
		const size_t size = current.inputs.size();
		const size_t half = size - (size >> 1);
		vector<int> left(current.inputs.begin(), current.inputs.begin() + half);
		vector<int> right(current.inputs.begin() + half, current.inputs.end());
		vector<int> left_upper, left_lower, right_upper, right_lower;

		if (half < p) {
			to_TO(top_id, clset, left_lower, left);
		} else {
			un = half / p;
			if (k >= 0 && k / p < un) un = k / p;
			left_upper.resize(un);
			for (int& lit : left_upper) lit = ++top_id;
			left_lower.resize(p - 1);
			for (int& lit : left_lower) lit = ++top_id;
		}
		if (right.size() < p) {
			to_TO(top_id, clset, right_lower, right);
		} else {
			un = right.size() / p;
			if (k >= 0 && k / p < un) un = k / p;
			right_upper.resize(un);
			for (int& lit : right_upper) lit = ++top_id;
			right_lower.resize(p - 1);
			for (int& lit : right_lower) lit = ++top_id;
		}

		mto_MUA_A(top_id, clset, current.upper, current.lower,
				left_upper, left_lower, right_upper, right_lower, p);
		if (half >= p)
			stack.push_back(Frame{std::move(left), std::move(left_upper), std::move(left_lower)});
		if (right.size() >= p)
			stack.push_back(Frame{std::move(right), std::move(right_upper), std::move(right_lower)});
	}
}

//
//=============================================================================
inline void mto_comparator(
	int& top_id,
	ClauseSet& clset,
	vector<int>& upper,
	vector<int>& lower,
	size_t p,
	int k
)
{
	size_t ro = k / p;
	size_t nu = k % p;

	// upper
	for (size_t i = ro + 1; i <= upper.size(); i++)
		clset.create_unit_clause(-upper[i - 1]);

	// lower
	for (size_t i = nu + 1; i < p; i++) {
		if (ro > 0) {
			if (ro - 1 < upper.size())
				clset.create_binary_clause(-upper[ro - 1], -lower[i - 1]);
		}
		else
			clset.create_unit_clause(-lower[i - 1]);
	};
}

//
//=============================================================================
inline void mto_encode_atmostN(
	int& top_id,
	ClauseSet& clset,
	vector<int>& vars,
	int k
)
{
	size_t n = vars.size();

	if ((size_t)k >= n)
		return;

	if (k == 0) {
		// generate \sum x <= 0
		common_encode_atmost0(clset, vars);
		return;
	}

	size_t p = (size_t)floor(sqrt((double)n));
	if (p < 2)
		p = 2;

	vector<int> uvars, lvars;
	mto_MTO_A(top_id, clset, uvars, lvars, vars, p);
	mto_comparator(top_id, clset, uvars, lvars, p, k);
}

//
//=============================================================================
inline void mto_encode_atleastN(
	int& top_id,
	ClauseSet& clset,
	vector<int>& vars,
	int tval
)
{
	vector<int> ps;
	int nrhs = -tval;
	for (size_t i = 0; i < vars.size(); i++) {
		nrhs += 1; // the weight in fact
		ps.push_back(-vars[i]);
	}

	mto_encode_atmostN(top_id, clset, ps, nrhs);
}

// approximation of k modulo totalizer
//=============================================================================
inline void kmto_encode_atmostN(
	int& top_id,
	ClauseSet& clset,
	vector<int>& vars,
	int k
)
{
	size_t n = vars.size();

	if ((size_t)k >= n)
		return;

	if (k == 0) {
		// generate \sum x <= 0
		common_encode_atmost0(clset, vars);
		return;
	}

	size_t p = (size_t)floor(sqrt((double)k));
	if (p < 2)
		p = 2;

	vector<int> uvars, lvars;
	mto_MTO_A(top_id, clset, uvars, lvars, vars, p, k);
	mto_comparator(top_id, clset, uvars, lvars, p, k);
}

//
//=============================================================================
inline void kmto_encode_atleastN(
	int& top_id,
	ClauseSet& clset,
	vector<int>& vars,
	int tval
)
{
	vector<int> ps;
	int nrhs = -tval;

	for (size_t i = 0; i < vars.size(); i++) {
		nrhs += 1; // the weight in fact
		ps.push_back(-vars[i]);
	}

	kmto_encode_atmostN(top_id, clset, ps, nrhs);
}

//
//=============================================================================
inline void kmto_encode_equalsN(
	int& top_id,
	ClauseSet& clset,
	vector<int>& vars,
	int k
)
{
	kmto_encode_atmostN (top_id, clset, vars, k);
	kmto_encode_atleastN(top_id, clset, vars, k);
}

#endif // MTO_HH_
