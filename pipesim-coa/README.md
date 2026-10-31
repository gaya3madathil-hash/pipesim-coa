# PipeSim — a 5-stage pipelined CPU & cache simulator

[![CI](https://github.com/<your-username>/pipesim-coa/actions/workflows/ci.yml/badge.svg)](https://github.com/<your-username>/pipesim-coa/actions)

A small, readable, **cycle-accurate** simulator built for studying
**Computer Organisation & Architecture**. Write MIPS-style assembly, run it through a
classic IF → ID → EX → MEM → WB pipeline, and *see* what data hazards, forwarding,
branch penalties and cache misses do to your CPI.

Pure Python 3.9+, **zero dependencies**, ~500 lines of core code, fully unit-tested.

```
 ┌────┐   ┌────┐   ┌────┐   ┌─────┐   ┌────┐
 │ IF │──▶│ ID │──▶│ EX │──▶│ MEM │──▶│ WB │
 └────┘   └────┘   └────┘   └─────┘   └────┘
 fetch    decode   ALU /    data      register
          + hazard branch   cache     write
          detect   resolve  access
              ▲       │  forwarding paths  │
              └───────┴────────────────────┘
```

## COA concepts demonstrated

| Topic | Where to look |
|---|---|
| Instruction set design & assembly | `pipesim/isa.py` |
| 5-stage pipelining, pipeline registers | `pipesim/cpu.py` |
| RAW data hazards, stalls, **data forwarding** | `CPU._forward`, `CPU._must_stall` |
| Load-use hazard (the one forwarding can't fix) | `examples/sum_array.asm` |
| Control hazards, predict-not-taken, flushing | taken branch = 2-cycle penalty, jump = 1 |
| CPI, speed-up, the cycle-accounting identity | `--compare`, `tests/` |
| Cache organisation: direct-mapped → set-associative, LRU | `pipesim/cache.py` |
| Spatial locality, conflict misses, write-back / write-allocate | `cache --sweep` |
| Miss penalty & memory stalls in the pipeline | `run --cache` |

## Quick start

```bash
git clone https://github.com/<your-username>/pipesim-coa.git
cd pipesim-coa

python -m pipesim run examples/sum_array.asm --compare
python -m pipesim run examples/raw_hazards.asm --no-forwarding --diagram
python -m pipesim run examples/matrix_walk.asm --cache --block-size 16
python -m pipesim cache --pattern stride --stride 256 --sweep

python -m pytest            # run the tests (pip install pytest)
```

### Forwarding vs. no forwarding

```
$ python -m pipesim run examples/sum_array.asm --compare
configuration       cycles   instr     CPI  stalls  br.pen
no forwarding           91      56   1.625      21      10
with forwarding         78      56   1.393       8      10

Forwarding speed-up: 1.17x
```

### Pipeline timing diagram (`--diagram`)

`X*` marks a stall (the stage is repeated). Here, with forwarding **disabled**, every
dependent instruction waits in ID until its producer has written back:

```
instruction               1    2    3    4    5    6    7    8    9    10   11
li   $t0, 5               IF   ID   EX   MEM  WB
li   $t1, 7                    IF   ID   EX   MEM  WB
add  $t2, $t0, $t1                  IF   ID   ID*  ID*  EX   MEM  WB
sub  $t3, $t2, $t0                       IF   ID   ID*  ID*  EX   MEM  WB
...
```

With forwarding on, the same code has **zero** stalls (try it without `--no-forwarding`).

## The assembly language

MIPS-like, 32 registers (`$zero`, `$t0`–`$t9`, `$s0`–`$s7`, `$a0`–`$a3`, … or `$0`–`$31`, `r0`–`r31`).

| Kind | Instructions |
|---|---|
| ALU (R-type) | `add sub and or slt mul rd, rs, rt` |
| ALU (immediate) | `addi andi ori slti rd, rs, imm` |
| Memory | `lw rd, off(rs)` · `sw rt, off(rs)` (word-aligned, byte addresses) |
| Control | `beq/bne rs, rt, label` · `j label` |
| Pseudo | `li rd, imm` · `la rd, label` · `move rd, rs` · `nop` · `halt` |
| Directives | `.data` `.text` `.word a, b, c` `.space nwords` · comments with `#` or `;` |

## Microarchitecture details

* **Register file** writes in the first half of a cycle and reads in the second, so a WB→ID dependence costs nothing.
* **Hazard unit** (in ID). Without forwarding it stalls until the producer reaches WB; with forwarding only a **load-use** pair stalls (1 cycle).
* **Forwarding** paths: EX/MEM→EX and MEM/WB→EX, for both ALU operands (and store data).
* **Branches** resolve in EX with *predict-not-taken*: a taken branch squashes 2 instructions. **Jumps** resolve in ID (1 bubble).
* **Cache** (optional `--cache`): set-associative, LRU, write-back + write-allocate. A miss freezes the pipeline for `--miss-penalty` cycles (plus the same again to write back a dirty victim).
* Invariant checked by the tests: `cycles = retired + 4 + data_stalls + branch_penalty` (+ cache stalls).

## Cache studies

```
$ python -m pipesim cache --pattern stride --stride 256 --n 2000 --sweep
 assoc  sets  hit rate
     1    16      0.0%
     2     8      0.0%
```

Things to try:

* `--pattern sequential` → 75% hits with 16 B blocks (1 miss + 3 hits per block). Double `--block-size` and watch it climb to 87.5%.
* Two addresses that collide in a direct-mapped cache (see `test_conflict_misses_direct_mapped_vs_2way`).
* `--pattern loop --working-set 128` vs `512` on a 256 B cache — the cliff when the working set stops fitting (and LRU's pathological behaviour on cyclic scans).

## Project layout

```
pipesim/
  isa.py      ISA, Instruction, two-pass assembler
  cpu.py      pipelined CPU, hazard detection, forwarding, timing diagram
  cache.py    set-associative cache + synthetic address generators
  cli.py      `python -m pipesim run|cache`
examples/     sample programs (.asm)
tests/        pytest suite (assembler, hazards, timing identity, cache)
.github/workflows/ci.yml
```

## Ideas for extending it

1. **Branch prediction** — add a 1-bit/2-bit predictor + BTB and compare against predict-not-taken.
2. **Branch resolution in ID** (1-cycle penalty) with extra forwarding.
3. **Instruction cache** and a two-level (L1/L2) hierarchy, AMAT calculation.
4. **Superscalar / out-of-order** issue (Tomasulo or a scoreboard).
5. A **web or Tkinter visualiser** for the pipeline diagram.

## License

MIT — see [LICENSE](LICENSE).
