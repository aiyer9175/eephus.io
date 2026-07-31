"""Cross-model duplicate-constant scanner. READ-ONLY."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = ('__pycache__', '.git', '.cache', 'node_modules')


def files():
    for p in ROOT.rglob('*'):
        if not p.is_file() or any(s in p.parts for s in SKIP):
            continue
        if p.suffix not in ('.py', '.js', '.html', '.yaml', '.yml'):
            continue
        yield p


def scan(pat, label, maxper=6):
    rx = re.compile(pat)
    hits = {}
    for p in files():
        try:
            t = p.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        for i, line in enumerate(t.splitlines(), 1):
            if rx.search(line):
                key = p.relative_to(ROOT).as_posix()
                hits.setdefault(key, []).append((i, line.strip()[:170]))
    print('#' * 70)
    print('##', label, '--', len(hits), 'files')
    for f, v in sorted(hits.items()):
        print('===', f, '(%d)' % len(v))
        for i, l in v[:maxper]:
            print('  %6d %s' % (i, l))
    return hits


PATS = {
    'levels': (r'["\'](DSL|CPX|ROK|A\-|A\+|AAA)["\']\s*:\s*-?[\d.]', 'LEVEL-KEYED CONSTANT TABLES'),
    'pos': (r'["\'](SS|CF|1B|DH)["\']\s*:\s*-?[\d.]', 'POSITION-KEYED CONSTANT TABLES'),
    'plus': (r'100(\.0)?\s*\+\s*10(\.0)?\s*\*', 'PLUS-METRIC 100+10z FORMULA'),
    'repl': (r'REPLACEMENT_|replacement_level|REPL_LEVEL', 'REPLACEMENT LEVEL'),
    'aging': (r'AGE_|_AGING|aging_delta|age_curve|AGE_CURVE|peak_age|PEAK_AGE', 'AGING CURVES'),
    'park': (r'PARK_FACTOR|park_factor|_PF\b|park_fx', 'PARK FACTORS'),
    'discount': (r'discount_rate|DISCOUNT_RATE|0\.08\b|0\.10\b', 'DISCOUNT RATE'),
}

if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    for k, (pat, label) in PATS.items():
        if which in ('all', k):
            scan(pat, label)
