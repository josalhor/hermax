
#include "ACNFRunner.h"

#include "CNFReader.h"

using namespace std;
using namespace Aperture;

template <ValidLiteral TLit, ValidWeight TWeight>
int ACNFRunner<TLit, TWeight>::Run(const string& acnf_file_path,
                                   SolverType solver_type,
                                   bool strict_user_vars,
                                   SolverOptions& solver_options) {
  signal(SIGINT, print_results_and_exit);
  signal(SIGTERM, print_results_and_exit);

  Reset();

  // Solver initialization

  unordered_map<string, string> sat_solver_params;
  if (!solver) {
    solver = make_unique<Solver<TLit, TWeight>>(solver_type, sat_solver_params,
                                                solver_options);
  }

  // ACNF Parsing

  CNFReader reader(acnf_file_path);
  vector<TLit> lits;
  vector<pair<TWeight, TLit>> wlits;
  vector<TLit> assumps;
  int line_number = 0;

  auto TruncateSpaces = [&]() {
    while ((*reader >= 9 && *reader <= 13) || *reader == 32) ++reader;
  };

  auto SkipLine = [&]() {
    while (*reader != '\n' && *reader != EOF) ++reader;
    ++reader;
  };

  auto IsEOL = [&]() { return *reader == '\n' || *reader == EOF; };

  auto IsDigit = [&]() { return *reader >= '0' && *reader <= '9'; };

  auto ParseNum = [&](bool is_literal = false) -> int64_t {
    TruncateSpaces();
    if (IsEOL()) return static_cast<int64_t>(0);

    bool neg = (*reader == '-');
    if (neg) ++reader;

    int64_t num = 0;
    while (IsDigit()) num = num * 10 + (*reader - '0'), ++reader;

    if (*reader != ' ' && *reader != '\n' && *reader != EOF) {
      throw invalid_argument("Invalid character '" + string(1, *reader) +
                             "' while parsing number at line " +
                             to_string(line_number) + ".");
    }

    if (is_literal && !strict_user_vars && num > 0) {
      while (static_cast<size_t>(num) > user_vars.size())
        user_vars.push_back(solver->NewVar());
    }

    if (num == 0) return static_cast<int64_t>(0);

    if (neg) {
      num = -num;
    }

    return num;
  };

  auto ParseLit = [&]() {
    int64_t num = ParseNum(true);
    if (num < numeric_limits<TLit>::min() ||
        num > numeric_limits<TLit>::max()) {
      throw invalid_argument("Literal " + to_string(num) + " at line " +
                             to_string(line_number) +
                             " is out of bounds for the literal type.");
    }
    return static_cast<TLit>(num);
  };

  auto ParseWeight = [&]() {
    int64_t num = ParseNum();
    if (num < 0) {
      throw invalid_argument("Weight " + to_string(num) + " at line " +
                             to_string(line_number) + " cannot be negative.");
    }
    return static_cast<TWeight>(num);
  };

  auto ParseNumOfLits = [&]() {
    int64_t num = ParseNum();
    if (num < 0) {
      throw invalid_argument("Number of literals " + to_string(num) +
                             " at line " + to_string(line_number) +
                             " cannot be negative.");
    }
    return num;
  };

  auto UserLit = [&](TLit lit) -> TLit {
    return (lit > 0) ? user_vars[lit - 1] : -user_vars[-lit - 1];
  };

  auto ParseLits = [&]() {
    while (!IsEOL()) {
      TLit lit = ParseLit();
      if (lit == 0) break;
      lits.push_back(UserLit(lit));
    }
  };

  auto ParseWLits = [&]() {
    while (!IsEOL()) {
      TWeight weight = ParseWeight();
      if (weight == 0) break;
      TLit lit = ParseLit();
      if (lit == 0) {
        throw invalid_argument("Expected a literal after weight " +
                               to_string(weight) + " at line " +
                               to_string(line_number) + ".");
      }
      wlits.emplace_back(weight, UserLit(lit));
    }
  };

  auto ParseNumOfAssumps = [&]() {
    int64_t num = ParseNum();
    if (num < 0) {
      throw invalid_argument("Number of assumptions " + to_string(num) +
                             " at line " + to_string(line_number) +
                             " cannot be negative.");
    }
    return num;
  };

  auto ParseAssumps = [&]() {
    while (!IsEOL()) {
      TLit lit = ParseLit();
      if (lit == 0) break;
      assumps.push_back(UserLit(lit));
    }
  };

  auto ParseAmountLits = [&](int64_t count) {
    for (int64_t i = 0; i < count; i++) {
      TLit lit = ParseLit();
      if (lit == 0) {
        throw invalid_argument("Expected " + to_string(count) +
                               " literals, but found only " + to_string(i) +
                               " at line " + to_string(line_number) + ".");
      }
      lits.push_back(UserLit(lit));
    }
  };

  auto ParseAmountAssumps = [&](int64_t count) {
    for (int64_t i = 0; i < count; i++) {
      TLit lit = ParseLit();
      if (lit == 0) {
        throw invalid_argument("Expected " + to_string(count) +
                               " assumptions, but found only " + to_string(i) +
                               " at line " + to_string(line_number) + ".");
      }
      assumps.push_back(UserLit(lit));
    }
  };

  auto ParseAmountWLits = [&](int64_t count) {
    for (int64_t i = 0; i < count; i++) {
      TWeight weight = ParseWeight();
      if (weight == 0) {
        throw invalid_argument("Expected " + to_string(count) +
                               " weighted literals, but found only " +
                               to_string(i) + " at line " +
                               to_string(line_number) + ".");
      }
      TLit lit = ParseLit();
      if (lit == 0) {
        throw invalid_argument("Expected a literal after weight " +
                               to_string(weight) + " at line " +
                               to_string(line_number) + ".");
      }
      wlits.emplace_back(weight, UserLit(lit));
    }
  };

  auto ParsePredicate = [&]() {
    TruncateSpaces();
    char pc = *reader;
    ++reader;
    switch (pc) {
      case '<': {
        if (*reader == '=') {
          ++reader;
          return Predicate::LEQ;
        } else {
          return Predicate::LT;
        }
      }
      case '=': {
        if (*reader == '=') {
          ++reader;
        }
        return Predicate::EQ;
      }
      case '>': {
        if (*reader == '=') {
          ++reader;
          return Predicate::GEQ;
        } else {
          return Predicate::GT;
        }
      }
      default:
        throw invalid_argument("Invalid predicate in CNF file.");
    }
  };

  // Parsing and Solving

  bool just_solved = false;
  while (*reader != EOF) {
    TruncateSpaces();
    lits.clear();
    wlits.clear();
    assumps.clear();

    if (just_solved) {
      if (solver_return_status == SolverStatus::ERROR) {
        throw runtime_error(solver->GetLatestErrorReason());
      }
    }

    just_solved = false;
    solver_return_status = SolverStatus::UNKNOWN;
    line_number++;

    if (*reader == '\n') {
      ++reader;
      continue;
    }

    if (*reader == 'c' || *reader == 'p') {
      SkipLine();
      continue;
    }

    if (*reader == 'n') {  // New Variable(s)
      ++reader;
      int64_t num_new_vars = ParseNum();
      if (num_new_vars <= 0) {
        throw invalid_argument("Number of new variables " +
                               to_string(num_new_vars) + " at line " +
                               to_string(line_number) + " must be positive.");
      }

      for (int64_t i = 0; i < num_new_vars; i++) {
        user_vars.push_back(solver->NewVar());
      }

      SkipLine();
      continue;
    }

    if (*reader == 'd') {  // Cardinality Constraint
      ++reader;
      ParseLits();
      Predicate pred = ParsePredicate();
      uint64_t rhs = ParseNum();
      TLit selector = ParseLit();
      selector = (selector == 0) ? 0 : UserLit(selector);
      optional<TLit> selector_opt =
          (selector != 0) ? optional<TLit>(selector) : nullopt;

      solver->AddCardinalityConstraint(lits, pred, rhs, selector_opt);

      SkipLine();
      continue;
    }

    if (*reader == 'D') {  // PB Constraint
      ++reader;
      ParseWLits();
      Predicate pred = ParsePredicate();
      uint64_t rhs = ParseNum();
      TLit selector = ParseLit();
      selector = (selector == 0) ? 0 : UserLit(selector);

      switch (pred) {
        case Predicate::LT:
          solver->AddConstraintLessThan(wlits, rhs, selector);
          break;
        case Predicate::LEQ:
          solver->AddConstraintLessThanEqual(wlits, rhs, selector);
          break;
        default:
          throw invalid_argument(
              "Invalid predicate for PB constraint at line " +
              to_string(line_number) +
              ". Only < and <= are supported for PB "
              "constraints in this format.");
      }

      SkipLine();
      continue;
    }

    if (*reader == 't') {  // Totalizer
      ++reader;
      TLit selector = ParseLit();
      selector = (selector == 0) ? 0 : UserLit(selector);
      uint64_t rhs_simplification = ParseNum();
      ParseLits();
      optional<uint64_t> rhs_simplification_opt =
          (rhs_simplification != 0) ? optional<uint64_t>(rhs_simplification)
                                    : nullopt;

      solver->GetTotalizer(lits, selector, rhs_simplification_opt);

      SkipLine();
      continue;
    }

    if (*reader == 'T') {  // Generalized Totalizer
      ++reader;
      TLit selector = ParseLit();
      selector = (selector == 0) ? 0 : UserLit(selector);
      uint64_t rhs_simplification = ParseNum();
      ParseWLits();
      optional<uint64_t> rhs_simplification_opt =
          (rhs_simplification != 0) ? optional<uint64_t>(rhs_simplification)
                                    : nullopt;

      solver->GetGenTotalizer(wlits, selector, rhs_simplification_opt);

      SkipLine();
      continue;
    }

    if (*reader == 's') {  // SAT Solving
      problem_type = ProblemType::SAT;
      ++reader;
      ParseAssumps();
      PrintSolvingMessage(problem_type, assumps.size());

      solver_return_status = solver->Solve(assumps);

      just_solved = true;
      PrintResults();
      SkipLine();
      continue;
    }

    if (*reader == 'u') {  // Unweighted MaxSAT Solving
      problem_type = ProblemType::MAXSAT;
      ++reader;
      int64_t assumptions_count = ParseNumOfAssumps();
      int64_t lits_count = ParseNumOfLits();
      ParseAmountAssumps(assumptions_count);
      ParseAmountLits(lits_count);
      PrintSolvingMessage(problem_type, assumps.size(), lits.size());

      solver_return_status = solver->SolveMaxSAT(assumps, lits, false);

      just_solved = true;
      PrintResults();
      SkipLine();
      continue;
    }

    if (*reader == 'w') {  // Weighted MaxSAT Solving
      problem_type = ProblemType::WEIGHTED_MAXSAT;
      ++reader;
      int64_t assumptions_count = ParseNumOfAssumps();
      int64_t wlits_count = ParseNumOfLits();
      ParseAmountAssumps(assumptions_count);
      ParseAmountWLits(wlits_count);
      PrintSolvingMessage(problem_type, assumps.size(), wlits.size());

      solver_return_status = solver->SolveWeightedMaxSAT(assumps, wlits, false);

      just_solved = true;
      PrintResults();
      SkipLine();
      continue;
    }

    if (*reader == 'g') {  // BlackBox Solving
      problem_type = ProblemType::BLACKBOX;
      ++reader;
      int64_t assumptions_count = ParseNumOfAssumps();
      int64_t lits_count = ParseNumOfLits();
      ParseAmountAssumps(assumptions_count);
      ParseAmountLits(lits_count);

      /* ------------------------------------- */

      auto PbFunc = [&](function<TLitValue(TLit)> LitValue,
                        void* user_ds) -> TWeight {
        TWeight cost = 0;
        int i = 0;
        for (TLit lit : lits) {
          if (i % 2 == 0) {
            if (LitValue(lit) == TLitValue::FALSE) {
              cost += i;
            }
          } else {
            if (LitValue(lit) == TLitValue::TRUE) {
              cost += i;
            }
          }
          i++;
        }
        return cost;
      };

      /* ------------------------------------- */

      PrintSolvingMessage(problem_type, assumps.size(), lits.size());

      solver_return_status = solver->SolveBlackBox(assumps, lits, PbFunc);

      just_solved = true;
      PrintResults();
      SkipLine();
      continue;
    }

    if (*reader == 'b') {  // OBV Solving
      problem_type = ProblemType::OBV;
      ++reader;
      int64_t assumptions_count = ParseNumOfAssumps();
      int64_t lits_count = ParseNumOfLits();
      ParseAmountAssumps(assumptions_count);
      ParseAmountLits(lits_count);
      PrintSolvingMessage(problem_type, assumps.size(), lits.size());

      solver_return_status = solver->SolveOBV(assumps, lits);

      just_solved = true;
      PrintResults();
      SkipLine();
      continue;
    }

    // Add Clause

    ParseLits();
    solver->AddClause(lits);
  }

  // Clauses or Cardinality constraints were added, but no solve line was found.
  if (!just_solved) {
    problem_type = ProblemType::SAT;
    PrintSolvingMessage(problem_type, 0);
    solver_return_status = solver->Solve();
    PrintResults();
  }

  return SolverStatusCode();
}

template <ValidLiteral TLit, ValidWeight TWeight>
void ACNFRunner<TLit, TWeight>::Reset() {
  user_vars.clear();
  problem_type = ProblemType::SAT;
  solver_return_status = SolverStatus::UNKNOWN;
}

template <ValidLiteral TLit, ValidWeight TWeight>
int ACNFRunner<TLit, TWeight>::SolverStatusCode() {
  switch (solver_return_status) {
    case SolverStatus::SAT:
      if ((problem_type == ProblemType::MAXSAT ||
           problem_type == ProblemType::WEIGHTED_MAXSAT) &&
          solver->IsLatestMaxSATOptimal()) {
        return 30;
      }
      return 10;
    case SolverStatus::UNSAT:
      return 20;
    default:
      return 0;
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
void ACNFRunner<TLit, TWeight>::PrintSolvingMessage(ProblemType problem_type,
                                                    size_t num_assumptions,
                                                    size_t num_literals) {
  logger.Log(
      "=================================================================="
      "===");
  switch (problem_type) {
    case ProblemType::SAT:

      logger.Log(kExternal, "Solving SAT under {} assumption(s).",
                 num_assumptions);
      break;
    case ProblemType::MAXSAT:
      logger.Log(kExternal,
                 "Solving Unweighted MaxSAT with {} literals under {} "
                 "assumption(s).",
                 num_literals, num_assumptions);
      break;
    case ProblemType::WEIGHTED_MAXSAT:
      logger.Log(kExternal,
                 "Solving Weighted MaxSAT with {} literals under {} "
                 "assumption(s).",
                 num_literals, num_assumptions);
      break;
    case ProblemType::BLACKBOX:
      logger.Log(kExternal,
                 "Solving BlackBox with {} observables under {} assumption(s).",
                 num_literals, num_assumptions);
      break;
    case ProblemType::OBV:
      logger.Log(kExternal,
                 "Solving OBV with {} targets under {} assumption(s).",
                 num_literals, num_assumptions);
      break;
  }
  logger.Log(
      "=================================================================="
      "===");
}

template <ValidLiteral TLit, ValidWeight TWeight>
void ACNFRunner<TLit, TWeight>::PrintModel(span<const TLitValue> model) {
  if (model.empty()) return;
  fmt::memory_buffer buffer;
  buffer.reserve(model.size());
  for (TLit v : user_vars) {
    buffer.push_back(model[v] == TLitValue::TRUE ? '1' : '0');
  }
  logger.LogV(kPrintRegardless, kExternal,
              fmt::string_view(buffer.data(), buffer.size()));
}

template <ValidLiteral TLit, ValidWeight TWeight>
void ACNFRunner<TLit, TWeight>::PrintValue(TWeight value) {
  logger.LogO(kPrintRegardless, kExternal, value);
}

template <ValidLiteral TLit, ValidWeight TWeight>
void ACNFRunner<TLit, TWeight>::PrintResults() {
  const auto& latest_solution = solver->GetLatestSolution();
  if (!latest_solution.empty() &&
      solver_return_status == SolverStatus::UNKNOWN) {
    solver_return_status = SolverStatus::SAT;
  }
  switch (solver_return_status) {
    case SolverStatus::SAT: {
      switch (problem_type) {
        case ProblemType::SAT:
        case ProblemType::OBV:
          logger.LogS(kPrintRegardless, kExternal, "SATISFIABLE");
          break;
        case ProblemType::MAXSAT:
        case ProblemType::WEIGHTED_MAXSAT: {
          if (solver->IsLatestMaxSATOptimal()) {
            logger.LogS(kPrintRegardless, kExternal, "OPTIMUM FOUND");
          } else {
            logger.LogS(kPrintRegardless, kExternal, "SATISFIABLE");
          }
          PrintValue(solver->GetLatestMaxSATValue());
          break;
        }
        case ProblemType::BLACKBOX:
          logger.LogS(kPrintRegardless, kExternal, "SATISFIABLE");
          PrintValue(solver->GetLatestBlackBoxValue());
          break;
      }
      PrintModel(latest_solution);
      break;
    }
    case SolverStatus::UNSAT:
      logger.LogS(kPrintRegardless, kExternal, "UNSATISFIABLE");
      break;
    case SolverStatus::ERROR:
      logger.LogS(kPrintRegardless, kExternal, "ERROR");
      break;
    case SolverStatus::GLOBAL_CONTRADICTION:
      logger.LogS(kPrintRegardless, kExternal, "GLOBAL CONTRADICTION");
      break;
    case SolverStatus::UNKNOWN:
      logger.LogS(kPrintRegardless, kExternal, "UNKNOWN");
      break;
  }
}

template class Aperture::ACNFRunner<int32_t, uint64_t>;