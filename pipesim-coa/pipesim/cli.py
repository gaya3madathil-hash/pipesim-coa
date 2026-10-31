"""Command-line interface: `python -m pipesim run|cache ...`"""
from __future__ import annotations

import argparse
import sys

from .cache import Cache, pattern_addresses
from .cpu import CPU, CPUError
from .isa import NAMES, AsmError, assemble


def _make_cache(a):
    return Cache(a.cache_size, a.block_size, a.assoc, a.miss_penalty) if a.cache else None


def _report(cpu: CPU, title: str) -> None:
    s = cpu.stats
    print(f"== {title} ==")
    print(f"  cycles            : {s.cycles}")
    print(f"  instructions      : {s.retired}")
    print(f"  CPI               : {s.cpi:.3f}")
    print(f"  data-hazard stalls: {s.data_stalls}")
    print(f"  branch penalty    : {s.branch_penalty} cycles ({s.taken}/{s.branches} branches taken)")
    if cpu.cache:
        print(f"  cache stall cycles: {s.mem_stall_cycles}")
        print(f"  cache             : {cpu.cache.describe()}")
        print(f"                      {cpu.cache.summary()}")


def cmd_run(a) -> int:
    with open(a.file, encoding="utf-8") as f:
        prog = assemble(f.read())

    if a.compare:
        rows = []
        for fwd in (False, True):
            cpu = CPU(prog, forwarding=fwd, cache=_make_cache(a), max_cycles=a.max_cycles)
            cpu.run()
            rows.append(("with forwarding" if fwd else "no forwarding", cpu.stats))
        print(f"{'configuration':<18}{'cycles':>8}{'instr':>8}{'CPI':>8}{'stalls':>8}{'br.pen':>8}")
        for name, s in rows:
            print(f"{name:<18}{s.cycles:>8}{s.retired:>8}{s.cpi:>8.3f}{s.data_stalls:>8}{s.branch_penalty:>8}")
        speedup = rows[0][1].cycles / rows[1][1].cycles
        print(f"\nForwarding speed-up: {speedup:.2f}x")
        return 0

    cpu = CPU(prog, forwarding=not a.no_forwarding, cache=_make_cache(a), max_cycles=a.max_cycles)
    cpu.run()
    if a.diagram:
        print(cpu.diagram(), "\n")
    _report(cpu, f"{a.file} ({'no ' if a.no_forwarding else 'with '}forwarding)")
    regs = [f"${NAMES[i]}={v}" for i, v in enumerate(cpu.regs) if v]
    print("\nNon-zero registers:", ", ".join(regs) or "(none)")
    if cpu.dmem:
        words = ", ".join(f"[{k}]={v}" for k, v in sorted(cpu.dmem.items())[:16])
        print("Data memory       :", words)
    return 0


def cmd_cache(a) -> int:
    def run(assoc: int) -> Cache:
        c = Cache(a.cache_size, a.block_size, assoc, a.miss_penalty)
        for addr in pattern_addresses(a.pattern, a.n, a.stride, working_set=a.working_set):
            c.access(addr)
        return c

    if a.sweep:
        print(f"pattern={a.pattern}, n={a.n}, {a.cache_size} B cache, {a.block_size} B blocks")
        print(f"{'assoc':>6}{'sets':>6}{'hit rate':>10}")
        for assoc in (1, 2, 4, 8):
            if a.cache_size % (a.block_size * assoc) == 0:
                c = run(assoc)
                print(f"{assoc:>6}{c.num_sets:>6}{c.hit_rate:>10.1%}")
    else:
        c = run(a.assoc)
        print(c.describe())
        print(c.summary())
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pipesim", description="5-stage pipeline + cache simulator")
    sub = p.add_subparsers(dest="command", required=True)

    def cache_args(q):
        q.add_argument("--cache-size", type=int, default=256, help="bytes (default 256)")
        q.add_argument("--block-size", type=int, default=16, help="bytes (default 16)")
        q.add_argument("--assoc", type=int, default=1, help="ways (default 1 = direct-mapped)")
        q.add_argument("--miss-penalty", type=int, default=10, help="cycles (default 10)")

    r = sub.add_parser("run", help="assemble and run a program on the pipeline")
    r.add_argument("file")
    r.add_argument("--no-forwarding", action="store_true", help="disable data forwarding")
    r.add_argument("--compare", action="store_true", help="compare forwarding vs. no forwarding")
    r.add_argument("--diagram", action="store_true", help="print the pipeline timing diagram")
    r.add_argument("--cache", action="store_true", help="attach a data cache")
    r.add_argument("--max-cycles", type=int, default=1_000_000)
    cache_args(r)
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("cache", help="study the cache on synthetic address streams")
    c.add_argument("--pattern", choices=["sequential", "stride", "random", "loop"], default="sequential")
    c.add_argument("--n", type=int, default=4096, help="number of accesses")
    c.add_argument("--stride", type=int, default=64, help="bytes, for the stride pattern")
    c.add_argument("--working-set", type=int, default=512, help="bytes, for the loop pattern")
    c.add_argument("--sweep", action="store_true", help="sweep associativity 1/2/4/8")
    cache_args(c)
    c.set_defaults(func=cmd_cache)
    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    try:
        sys.exit(args.func(args))
    except (AsmError, CPUError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
