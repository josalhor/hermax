<p align="center">
  <img src="assets/Aperture_Logo.svg" alt="Alt Text" width="500">
</p>

# Aperture: A SAT-based Optimization Tool

Aperture is an anytime and incremental SAT-based optimization tool that supports SAT solving and three SAT-based optimization paradigms: MaxSAT, Modulo Bit-Vector Optimization (OBV) and Black-Box Optimization.  Across all three paradigms, the solver is incremental and anytime, while it is complete for MaxSAT and OBV but incomplete for black-box optimization.
Aperture provides an in-memory C++ (native and IPAMIR) and Python API as well as a unified text input format called ACNF, which allows to specify clauses, constraints, encodings, and solve types in a flexible manner.

# Features

- <b>SAT Solving</b>: Solve Boolean satisfiability problems under assumptions.
- <b>MaxSAT Solving</b>: Solve unweighted and weighted MaxSAT problems under assumptions.
- <b>Modulo Bit-Vector Optimization (OBV)</b>: Optimize modulo bit-vector problems under assumptions.
- <b>Black-Box Optimization</b>: Optimize black-box problems under assumptions.
- <b>ACNF Input Format</b>: A unified input text format that allows to specify clauses, constraints, encodings, and solve types in a flexible manner.
- <b>Python API</b>: A Python API that allows to interact with the solver programmatically in python.

## MaxSAT Solving

For MaxSAT solving, Aperture also:

- <b>Supports the WCNF format</b>: which is a standard input format for MaxSAT problems in the MaxSAT community.
- <b>Anytime</b>: intermediate solutions are available (printed) during the solving process, and are guarenteed to be strictly improving overtime. The use can stop the solving process at any time and obtain the best solution found so far.
- <b>Complete</b>: the final (non-interrupted) solution for both weighted and unweighted problems is guaranteed to be optimal.
- <b>Incremental</b>: Aperture implements IPAMIR [1], which is a standard interface for incremental MaxSAT solvers. This allows to solve a sequence of related MaxSAT problems efficiently by reusing information from previous instances.

[1] A. Niskanen, J. Berg, and M. Järvisalo, “Incremental maximum satisfiability,” in 25th Inter-
national Conference on Theory and Applications of Satisfiability Testing (SAT 2022). Schloss
Dagstuhl–Leibniz-Zentrum für Informatik, 2022, pp. 14–1.

# Installation

In the root directory of the repository, the following cammands are available:

- `make`: build the solver as a standalone executable.
- `make rs`: build the solver as a standalone executable statically linked.
- `make ls`: build the solver as a static library.
- `make lp`: build the solver as a static library with the -fPIC flag.
- `make lpy`: build the python bindings for the solver. The module (shared library) will be in `aperture` directory. Note that Aperture uses nanobind for the python bindings, which requires it to be installed via `pip install nanobind`.

## Python API

Aperture also provides a Python API. It can be installed directly through pip:

```
pip install aperture-solver
```

# Usage

There are multiple ways to use Aperture, including the C++ API, the Python API, and the standalone executable. The following sections provide details on how to use each of these interfaces.

## API

For the C++ API, include the header file `src/Aperture.h` and link against the static library `libaperture.a` (or the shared library if you built it as a shared library). For the Python API, import the module `aperture`, examples of using the python API can be found in the notebook in `aperture/docs/notebooks`.

## CLI (Standalone Executable)

The standalone executable can be used by providing an input file in the ACNF or WCNF format. The default mode is WCNF. To select between modes, run with the mode flag:

- `-m acnf` for ACNF mode.
- `-m wcnf` for WCNF mode.

For example, to solve a problem specified in `input.acnf`, you can run:

```
./aperture -m acnf input.acnf
```

The solver can also be configured using an `.ini` file, such as `aperture.ini`, which is located in the root directory of the repository. The `.ini` file allows to configure solver parameters. Note that the `.ini` file is optional, and if it is not present, the solver will use the default configurations in `src/AOptions.h`. The `.ini` file can be used to configure solver parameters, instead of writing them manually in the command line when running the solver's executable.

## ACNF

The ACNF is an input file format for Aperture. It is a superset of the DIMACS CNF format, i.e. every valid (DIMACS) CNF file is also a valid ACNF file. The ACNF format also allows the following line formats:

| Operation                                                    | Line Prefix | Line Content                                                                                          | Example                                                                                                                                                                                                                      |
| ------------------------------------------------------------ | ----------- | ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Clause                                                       | $\emptyset$ | \<literals\> 0                                                                                        | 1 2 3 0 <br> add the clause $(x_1 \vee x_2 \vee x_3)$                                                                                                                                                                        |
| New Variable                                                 | n           | \<num_of_new_vars\> 0                                                                                 | n 1 0 <br> create 1 new variable                                                                                                                                                                                             |
| Cardinality Constraint                                       | d           | \<literals\> \<predicate\> \<right_hand_side\> \<optional_selector\> 0                                | d 1 2 3 <= 2 0 <br> the constraint $x_1 + x_2 + x_3 \leq 2$ with no selector                                                                                                                                                 |
| Pseudo-Boolean Constraint                                    | D           | \<weighted_literals\> \<predicate\> \<right_hand_side\> \<optional_selector\> 0                       | D 1 1 2 2 3 3 <= 2 0 <br> the constraint $1 \cdot x_1 + 2 \cdot x_2 + 3 \cdot x_3 \leq 2$ with no selector                                                                                                                   |
| Totalizer Encoding                                           | t           | \<selector\> \<rhs_simplification\> \<literals\> 0                                                    | t 4 2 1 -2 3 0 <br> Encode Totalizer for the literals $\{x_1,\neg x_2,x_3\}$ with the selector literal $x_4$ and perform right hand side simplification for cost $\leq 2$                                                    |
| Generalizer Totalizer Encoding                               | T           | \<selector\> \<rhs_simplification\> \<weighted_literals\> 0                                           | t 4 3 1 1 2 -2 3 3 0 <br> Encode Generalized Totalizer for the weighted literals $\{1 \cdot x_1,2 \cdot \neg x_2,3 \cdot x_3\}$ with the selector literal $x_4$ and perform right hand side simplification for cost $\leq 3$ |
| Solve SAT Under Assumptions                                  | s           | \<assumptions\> 0                                                                                     | s 1 2 3 0 <br> solve SAT under the assumptions: $\{x_1,x_2,x_3\}$                                                                                                                                                            |
| Solve Unweighted MaxSAT Under Assumptions                    | u           | \<num_of_assumptions\> \<num_of_soft_literals\> \<assumptions\> \<soft_literals\> 0                   | u 1 3 1 1 -2 3 0 <br> solve Unweighted MaxSAT under 1 assumption: $\{x_1\}$ for the 3 soft literals: $\{x_1, \neg x_2, x_3\}$                                                                                                |
| Solve Weighted MaxSAT Under Assumptions                      | w           | \<num_of_assumptions\> \<num_of_weighted_soft_literals\> \<assumptions\> \<weighted_soft_literals\> 0 | w 1 3 1 1 1 -2 2 3 3 0 <br> solve Unweighted MaxSAT under 1 assumption: $\{x_1\}$ for the 3 weighted soft literals: $\{1 \cdot x_1, 2 \cdot \neg x_2, 3 \cdot x_3\}$                                                         |
| Solve Modulo Bit-Vector Optimization (OBV) Under Assumptions | b           | \<num_of_assumptions\> \<num_of_targets\> \<assumptions\> \<targets\> 0                               | b 1 3 1 2 3 0 <br> solve OBV under 1 assumption: $\{x_1\}$ for the 3 targets: $\{x_1, x_2, x_3\}$                                                                                                                            |
| Solve Black-Box Optimization Under Assumptions               | g           | \<num_of_assumptions\> \<num_of_observables\> \<assumptions\> \<observables\> 0                       | g 1 3 1 2 3 0 <br> solve Black-Box under 1 assumption: $\{x_1\}$ for the 3 observables: $\{x_1, x_2, x_3\}$                                                                                                                  |

If there is no solve type line after adding clause(s), constraint(s) or encoding(s), the solver will perform a SAT solving under no assumptions.

# Testing

Aperture is tested using both unit tests and fuzz testing.

## API

For the API tests we used googletest (which is included). Run `make build-tests -j` to build the test executable in the `build` directory. To run the tests, execute `make run-tests -j`. Similar tests to the python API are also included in the `aperture/tests` directory, which can be run by executing `pytest` in the directory.

## CLI - Fuzz Testing

Since covering every edge case is difficult, we also used fuzz testing.
For non-incremental anytime MaxSAT solving (i.e., CLI mode with WCNF) we used [MaxSAT Fuzzer](https://github.com/tobipaxe/MaxSAT-Fuzzer) to generate random MaxSAT instances and compare the results of different configurations of Aperture and another baseline solver, [EvalMaxSAT (2022)](https://github.com/normal-account/EvalMaxSAT2022). To run it against Aperture, compile Aperture as an executable by running `make -j` and follow the instructions in the repository.

For incremental MaxSAT solving, we implemented a custom fuzzer that generates random sequences of incremental SAT and MaxSAT queries in Aperture's ACNF format. We then compare the results of different configurations of Aperture and EvalMaxSAT (2022). For the queries against EvalMaxSAT, we first parse each query and all of the previously added clauses as WCNF instances with the soft literals added as negated unit soft clauses and assumptions as unit hard clauses, and then run each WCNF instance against it. The fuzzer is located in `external/acnfuzz`, run `./make_acnfuzz.sh` inside the directory to compile the fuzzer. A simple running and comparison script is supplied, to run the fuzzing process, first compile Aperture as an executable by running `make -j` and run it with the script: `python3 run_acnfuzz.py --iterations <num_iterations>`. There are two configurations of Aperture ready in `external/acnfuzz/solvers`, as well as the binary of EvalMaxSAT.

# Experimental Results

This section describes how to reproduce the experimental results for both non-incremental and incremental MaxSAT solving as described in SOFT'26 and POS'26 workshop contributions.

## Non-incremental MaxSAT

To reproduce the experimental results for non-incremental MaxSAT, compile Aperture as an executable by running `make -j` and run it against (each instance of) the MaxSAT evaluation (MSE) anytime benchmarks of [MSE 2022 (was called 'incomplete')](https://maxsat-evaluations.github.io/2022/benchmarks.html), [MSE 2023](https://maxsat-evaluations.github.io/2023/benchmarks.html) and [MSE 2024](https://maxsat-evaluations.github.io/2024/benchmarks.html). To run the specific configurations described in SOFT'26 and POS'26 workshop contributions, use the following options:

- Aperture-Glucose:
  - Weighted: `./build/aperture_static <input_file> -s glucose opti -i --initial-solver kissat`
  - Unweighted: `./build/aperture_static <input_file> -s glucose`
- Aperture-IntelSAT:
  - Weighted: `./build/aperture_static <input_file> -s topor opti -i --initial-solver kissat`
  - Unweighted: `./build/aperture_static <input_file> -s topor`

All other options (and technically, some of the above) are set by the CLI runner or to their default values.

As described, we also ran it against [tt-open-wbo-inc](https://github.com/alexander-nadel-academic/tt-open-wbo-inc/) and the winners of the MSE 2024: [SPB-MaxSAT-c-FPS (download)](https://maxsat-evaluations.github.io/2024/mse24-solver-src/anytime/SPB-MaxSAT-c-FPS.zip) and [SPB-MaxSAT-c-Band (download)](https://maxsat-evaluations.github.io/2024/mse24-solver-src/anytime/SPB-MaxSAT-c-Band.zip). You can find the source code for all solvers in the MSE 2024 website. Note that tt-open-wbo-inc need to be compiled twice, once with Glucose as SAT solver, and once with IntelSAT. All of their configurations are the defualt ones. Run each solver against each benchmark, similarly to the above.

## Incremental MaxSAT

For inremental MaxSAT, we ran Aperture against the incremental benchmark from MSE 2022. To reproduce the results, compile Aperture as a static library using `make ls -j`, go to the [IPAMIR Repository](https://bitbucket.org/coreo-group/ipamir/src/master/) and follow the instructions to link Aperture, compile all of the other solvers, and run the incremental benchmarks.
