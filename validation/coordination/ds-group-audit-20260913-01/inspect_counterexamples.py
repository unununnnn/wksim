"""Inspect the independent review's counterexample streams (read-only)."""
import json, os, sys, hashlib

W = sys.argv[1]
EXPECTED = {
    'rate.jsonl': '7aa7e3f4624a5128d1301e6ca1f7d4baaa239357d920154a185546a496202d01',
    'rate-e1.jsonl': 'c5237fef69accce79ec24fd84de0c141a68ff196d0d057c78ce0b5f73dc2d8ad',
    'rate-e2.jsonl': '17ba3ef49db94d7e422ec8ba2ba63bacc723418fc660a4a91322d681bfd75b98',
    'rate-e3.jsonl': 'b81c35cfdbaa1da1fe8d147784a50f835cf6cf948e84b9f5c8db970fad2a97b6',
    'rate-e4.jsonl': 'bb6c8fbcccb868b382e7f72ce3cd6c851d260fa307413c4b1513889e714496c2',
}
for name, expected in EXPECTED.items():
    path = os.path.join(W, name)
    digest = hashlib.sha256(open(path, 'rb').read()).hexdigest()
    kinds = []
    rows = []
    with open(path) as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            kinds.append(row['kind'])
            rows.append(row)
    counts = {}
    for kind in kinds:
        counts[kind] = counts.get(kind, 0) + 1
    print('== %s sha %s (%s) rows %d' % (name, digest[:12], 'MATCH' if digest == expected else 'DIFFER', len(rows)))
    print('   kinds', counts)
    if len(rows) <= 40:
        for row in rows:
            print('   %-18s tick=%-7s seg=%-3s start=%-7s end=%-7s' % (
                row['kind'], row.get('tick'), row.get('segment_id'),
                row.get('start_tick'), row.get('end_tick')))
    else:
        # show the transitions relevant to ordering: first/last of each kind block
        order = [(i, r['kind'], r.get('tick')) for i, r in enumerate(rows)]
        print('   first 6', order[:6])
        print('   last 6', order[-6:])
        # detect a kind block boundary crossing
        transitions = [(a[1], b[1]) for a, b in zip(order, order[1:]) if a[1] != b[1]]
        print('   kind transitions', transitions[:12])
    print()
