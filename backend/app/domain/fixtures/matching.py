"""Maximum-weight matching on a general graph (Edmonds' blossom algorithm, Galil's O(n^3) formulation).

Own implementation following the classic primal-dual method; used by Swiss pairing to find the exact
minimum-cost rematch-free perfect matching. Integer weights only, so all dual arithmetic is exact.
"""


def max_weight_matching(edges: list[tuple[int, int, int]], maxcardinality: bool = False) -> list[int]:
    """edges: (i, j, weight). Returns mate[] where mate[v] is v's partner or -1."""
    if not edges:
        return []
    nedge = len(edges)
    nvertex = 1 + max(max(i, j) for i, j, _ in edges)
    maxweight = max(0, max(w for _, _, w in edges))
    endpoint = [edges[p // 2][p % 2] for p in range(2 * nedge)]
    neighbend = [[] for _ in range(nvertex)]
    for k, (i, j, _) in enumerate(edges):
        neighbend[i].append(2 * k + 1)
        neighbend[j].append(2 * k)
    mate = [-1] * nvertex
    label = [0] * (2 * nvertex)
    labelend = [-1] * (2 * nvertex)
    inblossom = list(range(nvertex))
    blossomparent = [-1] * (2 * nvertex)
    blossomchilds = [None] * (2 * nvertex)
    blossombase = list(range(nvertex)) + [-1] * nvertex
    blossomendps = [None] * (2 * nvertex)
    bestedge = [-1] * (2 * nvertex)
    blossombestedges = [None] * (2 * nvertex)
    unusedblossoms = list(range(nvertex, 2 * nvertex))
    dualvar = [maxweight] * nvertex + [0] * nvertex
    allowedge = [False] * nedge
    queue: list[int] = []

    def slack(k):
        i, j, wt = edges[k]
        return dualvar[i] + dualvar[j] - 2 * wt

    def leaves(b):
        if b < nvertex:
            yield b
        else:
            for t in blossomchilds[b]:
                if t < nvertex:
                    yield t
                else:
                    yield from leaves(t)

    def assign_label(w, t, p):
        b = inblossom[w]
        label[w] = label[b] = t
        labelend[w] = labelend[b] = p
        bestedge[w] = bestedge[b] = -1
        if t == 1:
            queue.extend(leaves(b))
        elif t == 2:
            base = blossombase[b]
            assign_label(endpoint[mate[base]], 1, mate[base] ^ 1)

    def scan_blossom(v, w):
        path = []
        base = -1
        while v != -1 or w != -1:
            b = inblossom[v]
            if label[b] & 4:
                base = blossombase[b]
                break
            path.append(b)
            label[b] = 5
            if labelend[b] == -1:
                v = -1
            else:
                v = endpoint[labelend[b]]
                b = inblossom[v]
                v = endpoint[labelend[b]]
            if w != -1:
                v, w = w, v
        for b in path:
            label[b] = 1
        return base

    def add_blossom(base, k):
        v, w, _ = edges[k]
        bb = inblossom[base]
        bv = inblossom[v]
        bw = inblossom[w]
        b = unusedblossoms.pop()
        blossombase[b] = base
        blossomparent[b] = -1
        blossomparent[bb] = b
        blossomchilds[b] = path = []
        blossomendps[b] = endps = []
        while bv != bb:
            blossomparent[bv] = b
            path.append(bv)
            endps.append(labelend[bv])
            v = endpoint[labelend[bv]]
            bv = inblossom[v]
        path.append(bb)
        path.reverse()
        endps.reverse()
        endps.append(2 * k)
        while bw != bb:
            blossomparent[bw] = b
            path.append(bw)
            endps.append(labelend[bw] ^ 1)
            w = endpoint[labelend[bw]]
            bw = inblossom[w]
        label[b] = 1
        labelend[b] = labelend[bb]
        dualvar[b] = 0
        for v in leaves(b):
            if label[inblossom[v]] == 2:
                queue.append(v)
            inblossom[v] = b
        bestedgeto = [-1] * (2 * nvertex)
        for bv in path:
            if blossombestedges[bv] is None:
                nblists = [[p // 2 for p in neighbend[v]] for v in leaves(bv)]
            else:
                nblists = [blossombestedges[bv]]
            for nblist in nblists:
                for kk in nblist:
                    i, j, _ = edges[kk]
                    if inblossom[j] == b:
                        i, j = j, i
                    bj = inblossom[j]
                    if bj != b and label[bj] == 1 and (bestedgeto[bj] == -1 or slack(kk) < slack(bestedgeto[bj])):
                        bestedgeto[bj] = kk
            blossombestedges[bv] = None
            bestedge[bv] = -1
        blossombestedges[b] = [kk for kk in bestedgeto if kk != -1]
        bestedge[b] = -1
        for kk in blossombestedges[b]:
            if bestedge[b] == -1 or slack(kk) < slack(bestedge[b]):
                bestedge[b] = kk

    def expand_blossom(b, endstage):
        for s in blossomchilds[b]:
            blossomparent[s] = -1
            if s < nvertex:
                inblossom[s] = s
            elif endstage and dualvar[s] == 0:
                expand_blossom(s, endstage)
            else:
                for v in leaves(s):
                    inblossom[v] = s
        if not endstage and label[b] == 2:
            entrychild = inblossom[endpoint[labelend[b] ^ 1]]
            j = blossomchilds[b].index(entrychild)
            if j & 1:
                j -= len(blossomchilds[b])
                jstep, endptrick = 1, 0
            else:
                jstep, endptrick = -1, 1
            p = labelend[b]
            while j != 0:
                label[endpoint[p ^ 1]] = 0
                label[endpoint[blossomendps[b][j - endptrick] ^ endptrick ^ 1]] = 0
                assign_label(endpoint[p ^ 1], 2, p)
                allowedge[blossomendps[b][j - endptrick] // 2] = True
                j += jstep
                p = blossomendps[b][j - endptrick] ^ endptrick
                allowedge[p // 2] = True
                j += jstep
            bv = blossomchilds[b][j]
            label[endpoint[p ^ 1]] = label[bv] = 2
            labelend[endpoint[p ^ 1]] = labelend[bv] = p
            bestedge[bv] = -1
            j += jstep
            while blossomchilds[b][j] != entrychild:
                bv = blossomchilds[b][j]
                if label[bv] == 1:
                    j += jstep
                    continue
                v = None
                for v in leaves(bv):
                    if label[v] != 0:
                        break
                if v is not None and label[v] != 0:
                    label[v] = 0
                    label[endpoint[mate[blossombase[bv]]]] = 0
                    assign_label(v, 2, labelend[v])
                j += jstep
        label[b] = labelend[b] = -1
        blossomchilds[b] = blossomendps[b] = None
        blossombase[b] = -1
        blossombestedges[b] = None
        bestedge[b] = -1
        unusedblossoms.append(b)

    def augment_blossom(b, v):
        t = v
        while blossomparent[t] != b:
            t = blossomparent[t]
        if t >= nvertex:
            augment_blossom(t, v)
        i = j = blossomchilds[b].index(t)
        if i & 1:
            j -= len(blossomchilds[b])
            jstep, endptrick = 1, 0
        else:
            jstep, endptrick = -1, 1
        while j != 0:
            j += jstep
            t = blossomchilds[b][j]
            p = blossomendps[b][j - endptrick] ^ endptrick
            if t >= nvertex:
                augment_blossom(t, endpoint[p])
            j += jstep
            t = blossomchilds[b][j]
            if t >= nvertex:
                augment_blossom(t, endpoint[p ^ 1])
            mate[endpoint[p]] = p ^ 1
            mate[endpoint[p ^ 1]] = p
        blossomchilds[b] = blossomchilds[b][i:] + blossomchilds[b][:i]
        blossomendps[b] = blossomendps[b][i:] + blossomendps[b][:i]
        blossombase[b] = blossombase[blossomchilds[b][0]]

    def augment_matching(k):
        v, w, _ = edges[k]
        for s, p in ((v, 2 * k + 1), (w, 2 * k)):
            while True:
                bs = inblossom[s]
                if bs >= nvertex:
                    augment_blossom(bs, s)
                mate[s] = p
                if labelend[bs] == -1:
                    break
                t = endpoint[labelend[bs]]
                bt = inblossom[t]
                s = endpoint[labelend[bt]]
                j = endpoint[labelend[bt] ^ 1]
                if bt >= nvertex:
                    augment_blossom(bt, j)
                mate[j] = labelend[bt]
                p = labelend[bt] ^ 1

    for _ in range(nvertex):
        label[:] = [0] * (2 * nvertex)
        bestedge[:] = [-1] * (2 * nvertex)
        blossombestedges[nvertex:] = [None] * nvertex
        allowedge[:] = [False] * nedge
        queue[:] = []
        for v in range(nvertex):
            if mate[v] == -1 and label[inblossom[v]] == 0:
                assign_label(v, 1, -1)
        augmented = False
        while True:
            while queue and not augmented:
                v = queue.pop()
                for p in neighbend[v]:
                    k = p // 2
                    w = endpoint[p]
                    if inblossom[v] == inblossom[w]:
                        continue
                    kslack = None
                    if not allowedge[k]:
                        kslack = slack(k)
                        if kslack <= 0:
                            allowedge[k] = True
                    if allowedge[k]:
                        if label[inblossom[w]] == 0:
                            assign_label(w, 2, p ^ 1)
                        elif label[inblossom[w]] == 1:
                            base = scan_blossom(v, w)
                            if base >= 0:
                                add_blossom(base, k)
                            else:
                                augment_matching(k)
                                augmented = True
                                break
                        elif label[w] == 0:
                            label[w] = 2
                            labelend[w] = p ^ 1
                    elif label[inblossom[w]] == 1:
                        b = inblossom[v]
                        if bestedge[b] == -1 or kslack < slack(bestedge[b]):
                            bestedge[b] = k
                    elif label[w] == 0:
                        if bestedge[w] == -1 or kslack < slack(bestedge[w]):
                            bestedge[w] = k
            if augmented:
                break
            deltatype = -1
            delta = deltaedge = deltablossom = None
            if not maxcardinality:
                deltatype = 1
                delta = min(dualvar[:nvertex])
            for v in range(nvertex):
                if label[inblossom[v]] == 0 and bestedge[v] != -1:
                    d = slack(bestedge[v])
                    if deltatype == -1 or d < delta:
                        delta, deltatype, deltaedge = d, 2, bestedge[v]
            for b in range(2 * nvertex):
                if blossomparent[b] == -1 and label[b] == 1 and bestedge[b] != -1:
                    d = slack(bestedge[b]) // 2
                    if deltatype == -1 or d < delta:
                        delta, deltatype, deltaedge = d, 3, bestedge[b]
            for b in range(nvertex, 2 * nvertex):
                if (blossombase[b] >= 0 and blossomparent[b] == -1 and label[b] == 2
                        and (deltatype == -1 or dualvar[b] < delta)):
                    delta, deltatype, deltablossom = dualvar[b], 4, b
            if deltatype == -1:
                deltatype = 1
                delta = max(0, min(dualvar[:nvertex]))
            for v in range(nvertex):
                if label[inblossom[v]] == 1:
                    dualvar[v] -= delta
                elif label[inblossom[v]] == 2:
                    dualvar[v] += delta
            for b in range(nvertex, 2 * nvertex):
                if blossombase[b] >= 0 and blossomparent[b] == -1:
                    if label[b] == 1:
                        dualvar[b] += delta
                    elif label[b] == 2:
                        dualvar[b] -= delta
            if deltatype == 1:
                break
            if deltatype == 2:
                allowedge[deltaedge] = True
                i, j, _ = edges[deltaedge]
                if label[inblossom[i]] == 0:
                    i, j = j, i
                queue.append(i)
            elif deltatype == 3:
                allowedge[deltaedge] = True
                i, j, _ = edges[deltaedge]
                queue.append(i)
            else:
                expand_blossom(deltablossom, False)
        if not augmented:
            break
        for b in range(nvertex, 2 * nvertex):
            if blossomparent[b] == -1 and blossombase[b] >= 0 and label[b] == 1 and dualvar[b] == 0:
                expand_blossom(b, True)

    for v in range(nvertex):
        if mate[v] >= 0:
            mate[v] = endpoint[mate[v]]
    return mate


def min_cost_perfect_matching(n: int, cost: dict[tuple[int, int], int]) -> list[tuple[int, int]] | None:
    """cost: {(i, j): non-negative int} for allowed pairs i < j. None if no perfect matching exists."""
    if n == 0:
        return []
    if n % 2 or not cost:
        return None
    big = max(cost.values()) + 1
    edges = [(i, j, big - c) for (i, j), c in cost.items()]
    mate = max_weight_matching(edges, maxcardinality=True)
    mate += [-1] * (n - len(mate))
    if any(m == -1 for m in mate[:n]):
        return None
    return [(i, mate[i]) for i in range(n) if i < mate[i]]
