#pragma once

#include <cstdint>

#define USE_TOPOR 1

namespace ToporWrapper
{
	// Variables, literals, lifted booleans (that is, values), copied from Glucose interface. 
	
	// There is a major API difference between Glucose and Topor w.r.t literals:
	// In Glucose's external API, for a variable v: the two positive and negative literals, respectively, are 2v and 2v+1
	// In Topor's external API, for a variable v: the two positive and negative literals, respectively, are v and -v (although, internally, it's similar to Glucose)
	// We won't risk changing the TLit type, since it might break the MaxSAT solver
	// We'll do all the mapping in CToporWrapper instead

	typedef int Var;
	#define var_Undef (-1)
	
	struct Lit {
		int     x;

		// Use this as a constructor:
		friend Lit mkLit(Var var, bool sign);

		bool operator == (Lit p) const { return x == p.x; }
		bool operator != (Lit p) const { return x != p.x; }
		bool operator <  (Lit p) const { return x < p.x;  } // '<' makes p, ~p adjacent in the ordering.
	};


	inline  Lit  mkLit     (Var var, bool sign = false) { Lit p; p.x = var + var + (int)sign; return p; }
	inline  Lit  operator ~(Lit p)              { Lit q; q.x = p.x ^ 1; return q; }
	inline  Lit  operator ^(Lit p, bool b)      { Lit q; q.x = p.x ^ (unsigned int)b; return q; }
	inline  bool sign      (Lit p)              { return p.x & 1; }
	inline  int  var       (Lit p)              { return p.x >> 1; }

	// Mapping Literals to and from compact integers suitable for array indexing:
	inline  int  toInt     (Var v)              { return v; } 
	inline  int  toInt     (Lit p)              { return p.x; } 
	inline  Lit  toLit     (int i)              { Lit p; p.x = i; return p; } 

	const Lit lit_Undef = { -2 };  // }- Useful special constants.
	const Lit lit_Error = { -1 };  // }

	#define l_True  (ToporWrapper::lbool((uint8_t)0)) // gcc does not do constant propagation if these are real constants.
	#define l_False (ToporWrapper::lbool((uint8_t)1))
	#define l_Undef (ToporWrapper::lbool((uint8_t)2))

	class lbool {
		uint8_t value;

	public:
		explicit lbool(uint8_t v) : value(v) { }

		lbool()       : value(0) { }
		explicit lbool(bool x) : value(!x) { }

		bool  operator == (lbool b) const { return ((b.value&2) & (value&2)) | (!(b.value&2)&(value == b.value)); }
		bool  operator != (lbool b) const { return !(*this == b); }
		lbool operator ^  (bool  b) const { return lbool((uint8_t)(value^(uint8_t)b)); }

		lbool operator && (lbool b) const { 
			uint8_t sel = (this->value << 1) | (b.value << 3);
			uint8_t v   = (0xF7F755F4 >> sel) & 3;
			return lbool(v); }

		lbool operator || (lbool b) const {
			uint8_t sel = (this->value << 1) | (b.value << 3);
			uint8_t v   = (0xFCFCF400 >> sel) & 3;
			return lbool(v); }

		friend int   toInt  (lbool l);
		friend lbool toLbool(int   v);
	};
	inline int   toInt  (lbool l) { return l.value; }
	inline lbool toLbool(int   v) { return lbool((uint8_t)v);  }
}
