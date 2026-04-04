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

#include <iostream>

#include "Instance.h"

using std::make_pair;
using std::cout;

void AF::addArgument(std::string arg)
{
    arg_to_int[arg] = args.size();
    args.push_back(arg);
}

void AF::addAttack(std::pair<std::string,std::string> att)
{
    attackers[arg_to_int[att.second]].push_back(arg_to_int[att.first]);
    atts.push_back(make_pair(arg_to_int[att.first], arg_to_int[att.second]));
    att_exists[make_pair(arg_to_int[att.first], arg_to_int[att.second])] = true;
}

void AF::addEnforcement(std::string arg)
{
    enfs.push_back(arg_to_int[arg]);
    enforce[arg_to_int[arg]] = true;
}

int AF::numberOfConflicts()
{
    int conflicts = 0;
    for (int i = 0; i < atts.size(); i++) {
        if (enforce[atts[i].first] && enforce[atts[i].second]) {
            conflicts++;
        }
    }
    return conflicts;
}

void AF::print()
{
    for (int i = 0; i < args.size(); i++) {
        cout << "arg(" << args[i] << ").\n";
    }
    for (int i = 0; i < atts.size(); i++) {
        cout << "att(" << args[atts[i].first] << "," << args[atts[i].second] << ").\n";
    }
}
