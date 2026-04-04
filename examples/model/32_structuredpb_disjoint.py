from hermax.encoder.pbamo import EncType, PBAMOEnc


def main() -> None:
    lits = [1, 2, 3, 4]
    weights = [2, 3, 4, 7]
    groups = [[1, 2], [3, 4]]
    bound = 8

    cnf = PBAMOEnc.leq(
        lits=lits,
        weights=weights,
        groups=groups,
        bound=bound,
        encoding=EncType.rggt,
    )

    print("encoding=rggt")
    print(f"nv={cnf.nv}")
    print(f"clauses={len(cnf.clauses)}")
    print("first_clauses=")
    for clause in cnf.clauses[:6]:
        print(clause)


if __name__ == "__main__":
    main()
