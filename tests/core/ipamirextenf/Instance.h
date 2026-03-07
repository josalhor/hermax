//  Copyright (c) 2022 Andreas Niskanen, University of Helsinki
//
//  Permission is hereby granted, free of charge, to any person obtaining a 
//  copy of this software and associated documentation files (the "Software"), 
//  to deal in the Software without restriction, including without limitation 
//  the rights to use, copy, modify, merge, publish, distribute, sublicense, 
//  and/or sell copies of the Software, and to permit persons to whom the 
//  Software is furnished to do so, subject to the following conditions:
//
//  The above copyright notice and this permission notice shall be included in 
//  all copies or substantial portions of the Software.
//
//  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS 
//  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
//  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE 
//  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
//  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING 
//  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
//  DEALINGS IN THE SOFTWARE.

#ifndef AF_INSTANCE_H
#define AF_INSTANCE_H

#include <vector>
#include <unordered_map>
#include <string>
#include <cstdint>

template <class T>
inline void hash_combine(std::size_t & seed, const T & v)
{
  std::hash<T> hasher;
  seed ^= hasher(v) + 0x9e3779b9 + (seed << 6) + (seed >> 2);
}

namespace std
{
  template<typename S, typename T> struct hash<pair<S, T>>
  {
    inline size_t operator()(const pair<S, T> & v) const
    {
      size_t seed = 0;
      ::hash_combine(seed, v.first);
      ::hash_combine(seed, v.second);
      return seed;
    }
  };
}

class AF {

public:
    std::vector<std::string> args;
    std::vector<std::pair<int,int>> atts;
    std::vector<int> enfs;
    std::unordered_map<int,std::vector<int>> attackers;
    std::unordered_map<std::pair<int,int>,bool> att_exists;
    std::unordered_map<std::string,int> arg_to_int;
    std::unordered_map<int,bool> enforce;

    void addArgument(std::string arg);
    void addAttack(std::pair<std::string,std::string> att);
    void addEnforcement(std::string arg);
    int numberOfConflicts();
    void print();

};

#endif
