#include "glucose3.cpp"
#include "satsolverinterface.hpp"


 //  g++ testsat.cpp -o testsat -Isolvers/glucose-3.0/  solvers/glucose-3.0/core/lib_standard.a 

void test(SATSolver* solver) {
	std::vector<std::vector<int> > clauses;
	clauses.push_back({0,2});
	clauses.push_back({0,4});
	

	solver->addClauses(clauses);


	std::vector<int> assumps={1};
	cout << (solver->solve(assumps)) << endl;
	assumps={1,3};
	cout << (solver->solve(assumps)) << endl;
	vector<int> core;
	solver->getCore(core);
	for (int i=0;i<core.size();++i) cout << core[i] << ", "; cout << endl;
}


int main() {
	Glucose3* solver = new Glucose3();
	test((SATSolver*)solver);
}
