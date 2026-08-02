#include "ArgParser.h"

#include <CLI/CLI.hpp>

using namespace std;
using namespace CLI;
using namespace Aperture;

pair<ExternalOptions, SolverOptions> ArgParser::ParseArgs(
    int argc, const char* const* argv) {
  ExternalOptions external_options;
  SolverOptions solver_options;

  App solver_args{"Aperture MaxSAT Solver Usage and Options"};

  solver_args.set_help_flag();
  solver_args.add_flag(
      "-h,--help", [&](bool) { throw CallForAllHelp(); }, "Print all help");
  solver_args.set_config("--config", "aperture.ini",
                         "Read configuration from an INI file", false);

  /* External arguments */

  auto StringViewIgnoreCaseFilter = [](std::string_view str) {
    std::string result(str);
    std::transform(result.begin(), result.end(), result.begin(),
                   [](unsigned char c) { return std::tolower(c); });
    return result;
  };

  solver_args.add_option("input_file", external_options.input_file,
                         "Path to the input ACNF/WCNF file");
  solver_args
      .add_option("-s,--solver", external_options.solver_type,
                  "Select SAT solver to use")
      ->transform(
          CheckedTransformer(kSolverTypeMap, StringViewIgnoreCaseFilter))
      ->description("SAT Solver: Topor, CaDiCaL, Glucose");
  solver_args
      .add_option("-m,--mode", external_options.mode, "Set operation mode")
      ->transform(
          CheckedTransformer(kSolverModeMap, StringViewIgnoreCaseFilter))
      ->description("Operation mode: ACNF, WCNF");
  solver_args.add_flag(
      "-u,--strict-user-vars", external_options.strict_user_vars,
      "For ACNF mode. If true, user variables must be created using the 'n' "
      "line prefix. If false, user variables will be created automatically. "
      "This is usefull for dumping the problem in ACNF format, so every API "
      "call including NewVar() will be reflected in the output file for "
      "debugging purposes.");

  /* Solver arguments */

  solver_args.add_option(
      "-v,--verbosity", solver_options.verbosity_level,
      "Set verbosity level (0 = silent, 1 = normal, 2 = verbose, 3 = very "
      "verbose)");
  solver_args.add_flag("--output-coloring", solver_options.output_coloring,
                       "Enable colored output in the terminal");

  // SAT-based optimization solving options

  auto* optimization_sub_command = solver_args.add_subcommand(
      "opti", "Options for SAT-based optimization solving.");
  optimization_sub_command->add_flag(
      "-i,--use-initial-solver", solver_options.use_initial_solver,
      "Use a different (possibly non-incremental) SAT solver in order to find "
      "the initial assignment");
  optimization_sub_command
      ->add_option(
          "--initial-solver", solver_options.initial_solver_type,
          "Select initial SAT solver: Topor, CaDiCaL, Glucose, Kissat)")
      ->transform(
          CheckedTransformer(kSolverTypeMap, StringViewIgnoreCaseFilter))
      ->description("Initial SAT Solver: Topor, CaDiCaL, Glucose, Kissat");
  optimization_sub_command->add_option(
      "-c,--conflict-threshold", solver_options.conflict_threshold,
      "Set conflict threshold for SAT solver calls");
  optimization_sub_command->add_option(
      "--polosat-max-epochs", solver_options.polosat_max_epochs,
      "Set maximum number of epochs for Polosat");
  optimization_sub_command->add_flag(
      "--polosat-update-bits-on-each-sat-model",
      solver_options.polosat_update_bits_on_each_sat_model,
      "Update Polosat target bits on each SAT model found");
  optimization_sub_command->add_flag(
      "--polosat-weighted-obv-strategy",
      solver_options.polosat_weighted_obv_strategy,
      "Use a weighted strategy for OBV in Polosat when called from MaxSAT "
      "solving (switch to OBV-BS in MS, but try standard MS call too, if "
      "OBV-BS failed to generate a model). Otherwise (unweighted case), the "
      "unweighted strategy will be used (use standard MS, but try OBV-BS too, "
      "if standard MS failed to generate a *better* model)");
  optimization_sub_command->add_flag(
      "--solve-optimistically", solver_options.solve_optimistically,
      "Enable optimistic solving  (targets polarities are "
      "fixed to FALSE)");
  optimization_sub_command->add_flag(
      "--solve-conservatively", solver_options.solve_conservatively,
      "Enable conservative solving  (non-targets are fixed "
      "to the best model polarities)");
  optimization_sub_command->add_flag("--use-target-bumping",
                                     solver_options.use_target_bumping,
                                     "Enable target literal score bumping");
  optimization_sub_command->add_option(
      "--max-bump-rand-val", solver_options.max_bump_rand_val,
      "Set the maximum random value for target literal score bumping");
  optimization_sub_command->add_option(
      "--target-bump-score-value", solver_options.target_bump_score_value,
      "Set the score bump value for target literals");

  // MaxSAT solving options

  auto* max_sat_sub_command =
      solver_args.add_subcommand("maxsat", "Options for MaxSAT solving.");
  max_sat_sub_command->add_flag(
      "--use-local-search", solver_options.use_local_search,
      "Enable the use of a local search solver in MaxSAT solving");
  max_sat_sub_command->add_flag("--use-sat-based-optimization",
                                solver_options.use_sat_based_optimization,
                                "Enable the use of SAT-based optimization in "
                                "MaxSAT solving (e.g. Mrs-Beaver)");
  max_sat_sub_command
      ->add_option("--local-search-solver-type",
                   solver_options.local_search_solver_type,
                   "Select local search solver type for MaxSAT solving: NuWLS, "
                   "DeepDist, Band")
      ->transform(CheckedTransformer(kLocalSearchSolverTypeMap,
                                     StringViewIgnoreCaseFilter))
      ->description("Local Search Solver Type: NuWLS, DeepDist, Band");
  max_sat_sub_command->add_flag(
      "-d,--disable-polosat", solver_options.disable_polosat,
      "Disable Polosat usage entirely (in MaxSAT solving)");
  max_sat_sub_command->add_flag(
      "--use-polosat-props-per-model-threshold",
      solver_options.use_polosat_props_per_model_threshold,
      "Enable the use of a threshold on the number of propagated literals per "
      "model in Polosat");
  max_sat_sub_command->add_option(
      "--max-props-per-model", solver_options.max_props_per_model,
      "Set the maximum number of propagated literals per model in Polosat");
  max_sat_sub_command->add_flag(
      "--use-polosat-model-per-sec-threshold",
      solver_options.use_polosat_model_per_sec_threshold,
      "Enable the use of a threshold on the number of models per second in "
      "Polosat");
  max_sat_sub_command->add_option(
      "--min-models-per-sec", solver_options.min_models_per_sec,
      "Set the minimum number of models per second in Polosat");

  // MaxSAT - MRS-Beaver options

  auto* mrs_beaver_group = max_sat_sub_command->add_option_group(
      "MRS-Beaver", "Options for MRS-Beaver MaxSAT Algorithm");
  mrs_beaver_group->add_option(
      "--mrs-beaver-max-iterations", solver_options.mrs_beaver_max_iterations,
      "Set the maximum number of iterations for MRS-Beaver");
  mrs_beaver_group->add_option(
      "--mrs-beaver-max-non-improving-iterations",
      solver_options.mrs_beaver_max_non_improving_iterations,
      "Set the maximum number of non-improving iterations for MRS-Beaver, "
      "before switching to complete part");
  mrs_beaver_group->add_option("--mrs-beaver-seed",
                               solver_options.mrs_beaver_seed,
                               "Set the random seed for MRS-Beaver");
  mrs_beaver_group->add_option(
      "--mrs-beaver-obv-conflict-threshold",
      solver_options.mrs_beaver_obv_conflict_threshold,
      "Set conflict threshold for SAT solver calls in OBV - MRS-Beaver");
  mrs_beaver_group->add_flag(
      "--mrs-beaver-use-complete-part-solver",
      solver_options.mrs_beaver_use_complete_part_solver,
      "Use a different SAT solver for the complete part in MRS-Beaver");
  mrs_beaver_group
      ->add_option("--mrs-beaver-complete-part-solver",
                   solver_options.mrs_beaver_complete_part_solver,
                   "Select complete part SAT solver for MRS-Beaver (Topor, "
                   "Glucose, CaDiCaL)")
      ->transform(
          CheckedTransformer(kSolverTypeMap, StringViewIgnoreCaseFilter))
      ->description(
          "Complete part SAT Solver for MRS-Beaver: Topor, Glucose, "
          "CaDiCaL");
  mrs_beaver_group->add_option(
      "--mrs-beaver-size-switch-to-complete",
      solver_options.mrs_beaver_size_switch_to_complete,
      "Set the size threshold to switch to complete part solver in "
      "MRS-Beaver");

  /* Parse */

  try {
    solver_args.parse(argc, argv);
  } catch (const ParseError& e) {
    exit(solver_args.exit(e));
  }

  if (external_options.input_file.empty()) {
    std::cout << "c Error: input file is required\n";
    std::cout << "c For more detailed help, use:\n";
    std::cout << "c   " << argv[0] << " --help\n";
    solver_args.help();
    exit(1);
  }
  return {external_options, solver_options};
}
