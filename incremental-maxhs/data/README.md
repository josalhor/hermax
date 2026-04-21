CP 2021 Paper Experiments
-------------------------

For the previous version of MaxHS, please check out the cp2021 tag by issuing:

```
git checkout cp2021
```

Full runtime data from the experiments reported on in the CP'21 paper can be
found in CSV form at ./dt-learning/results.csv and `./rule-learning/results.csv'.


SAT 2022 Paper Experiments
--------------------------

This version of MaxHS takes as input two files:

```
./src/build/release/bin/maxhs [options] <input-file> <index-file>
```

Here `<input-file>` is a plain or gzipped WCNF file containing the MaxSAT instance
and `<index-file>` is a file containing indices of soft clauses to be hardened.
(If a soft clause is the n:th soft clause in `<input-file>`, its index is n.)
In `<index-file>` each line is interpreted as an iteration, and all soft clauses
with indices on that line are hardened for that iteration.

To run different configurations of iMaxHS, use the following [options]:
* iMaxHS     : `-dsjnt-once -init-cores -conditional-cores`
* iMaxHS-NOI : `-dsjnt-once -no-init-cores -conditional-cores`
* iMaxHS-NOC : `-dsjnt-once -init-cores -no-conditional-cores`
* iMaxHS-DJA : `-no-dsjnt-once -init-cores -conditional-cores`

Full runtime data from the experiments reported on in the SAT'22 paper can be
found in CSV form at `./assumptions/results.csv`.
