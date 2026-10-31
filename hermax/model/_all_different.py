from collections import deque


def filter_domains(domains):
    """Return supported domains, or None if no matching exists."""
    n = len(domains)
    if not n:
        return domains
    first = domains[0]
    if all(domain == first for domain in domains):
        if len(first) < n:
            return None
        return domains
    # Every choice extends greedily when all domains have at least n values.
    if all(len(domain) >= n for domain in domains):
        return domains

    small = [i for i, domain in enumerate(domains) if len(domain) < n]
    if len(small) == n:
        analysis = _matching_filter(domains)
        return None if analysis is None else analysis[0]
    # Wide domains can accommodate any matching of the narrow domains.
    analysis = _matching_filter([domains[i] for i in small])
    if analysis is None:
        return None
    narrow, required = analysis
    supported = list(domains)
    for i, kept in zip(small, narrow):
        supported[i] = kept
    required = set(required)
    if required:
        for i, domain in enumerate(domains):
            if len(domain) >= n and any(value in domain for value in required):
                kept = [value for value in domain if value not in required]
                if len(kept) != len(domain):
                    supported[i] = kept
    return supported


def _matching_filter(domains):
    n = len(domains)
    values = tuple(dict.fromkeys(value for domain in domains for value in domain))
    indices = {value: i for i, value in enumerate(values)}
    rows = [[indices[value] for value in domain] for domain in domains]
    owner = [-1] * len(values)
    match = [-1] * n
    for start in range(n):
        queue = deque([start])
        via = {}
        end = -1
        while queue and end < 0:
            x = queue.popleft()
            for value in rows[x]:
                if value in via:
                    continue
                via[value] = x
                if owner[value] < 0:
                    end = value
                    break
                queue.append(owner[value])
        if end < 0:
            return None
        while end >= 0:
            x = via[end]
            previous = match[x]
            match[x] = end
            owner[end] = x
            end = previous

    graph = [[] for _ in range(n + len(values))]
    reverse = [[] for _ in graph]
    for x, row in enumerate(rows):
        for value in row:
            a, b = (n + value, x) if match[x] == value else (x, n + value)
            graph[a].append(b)
            reverse[b].append(a)

    # Alternating paths to spare values and alternating cycles preserve support.
    reachable = {n + value for value, x in enumerate(owner) if x < 0}
    stack = list(reachable)
    while stack:
        for node in reverse[stack.pop()]:
            if node not in reachable:
                reachable.add(node)
                stack.append(node)

    order, seen = [], set()
    for node in range(len(graph)):
        if node in seen:
            continue
        seen.add(node)
        stack = [(node, iter(graph[node]))]
        while stack:
            node, edges = stack[-1]
            child = next(edges, None)
            if child is None:
                order.append(node)
                stack.pop()
            elif child not in seen:
                seen.add(child)
                stack.append((child, iter(graph[child])))

    component = [-1] * len(graph)
    for root in reversed(order):
        if component[root] >= 0:
            continue
        component[root] = root
        stack = [root]
        while stack:
            for child in reverse[stack.pop()]:
                if component[child] < 0:
                    component[child] = root
                    stack.append(child)

    supported = []
    for x, row in enumerate(rows):
        kept = [values[v] for v in row if match[x] == v or n + v in reachable
                or component[x] == component[n + v]]
        supported.append(domains[x] if len(kept) == len(row) else kept)
    required = {value for i, value in enumerate(values) if n + i not in reachable}
    return supported, required
