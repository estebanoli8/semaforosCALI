"""Compare aggregate metrics for the same dataset and labels, without dependencies."""
import argparse
import json
import math
from pathlib import Path


def safe(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def compare(base, candidate):
    for key in ('dataset_id', 'labels_version'):
        if not base.get(key) or base[key] != candidate.get(key):
            raise ValueError(f'Comparación inválida: {key} debe existir y coincidir')
    lines = [f'# Comparación: {safe(base.get("run_id", "base"))} → {safe(candidate.get("run_id", "candidato"))}', '',
             '| Métrica | Base | Candidato | Diferencia | Resultado |',
             '|---|---:|---:|---:|---|']
    left, right = base.get('metrics', {}), candidate.get('metrics', {})
    for name in sorted(set(left) | set(right)):
        a, b = left.get(name, {}), right.get(name, {})
        x, y = a.get('value'), b.get('value')
        if x is None or y is None:
            lines.append(f'| {safe(name)} | {x} | {y} | — | Sin comparación |')
            continue
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (x, y)):
            raise ValueError(f'Valores no numéricos o no finitos: {name}')
        direction = a.get('direction')
        if direction not in ('higher', 'lower') or direction != b.get('direction'):
            raise ValueError(f'Dirección incompatible: {name}')
        delta = y - x
        result = 'Igual' if delta == 0 else ('Mejora' if (delta > 0) == (direction == 'higher') else 'Empeora')
        lines.append(f'| {safe(name)} | {x:g} | {y:g} | {delta:+.6g} | {result} |')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('base', type=Path)
    p.add_argument('candidate', type=Path)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    try:
        report = compare(json.loads(args.base.read_text()), json.loads(args.candidate.read_text()))
    except (ValueError, OSError, TypeError, AttributeError) as exc:
        p.error(str(exc))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding='utf-8')
    else:
        print(report, end='')
