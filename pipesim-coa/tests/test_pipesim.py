import os

import pytest

from pipesim import CPU, AsmError, Cache, assemble

EX = os.path.join(os.path.dirname(__file__), "..", "examples")


def load(name):
    with open(os.path.join(EX, name), encoding="utf-8") as f:
        return assemble(f.read())


def run(src_or_prog, **kw):
    prog = assemble(src_or_prog) if isinstance(src_or_prog, str) else src_or_prog
    cpu = CPU(prog, **kw)
    cpu.run()
    return cpu


# ---------------- assembler ----------------
def test_labels_and_pseudo_ops():
    p = assemble("start: li $t0, 5\n j start\n halt")
    assert p.labels["start"] == 0 and len(p.instructions) == 3
    assert p.instructions[0].op == "addi"


def test_assembler_errors():
    with pytest.raises(AsmError):
        assemble("frobnicate $t0")
    with pytest.raises(AsmError):
        assemble("add $t0, $t1")
    with pytest.raises(AsmError):
        assemble("j nowhere")


# ---------------- correctness ----------------
def test_raw_chain_results():
    for fwd in (True, False):
        cpu = run(load("raw_hazards.asm"), forwarding=fwd)
        assert (cpu.regs[10], cpu.regs[11], cpu.regs[12], cpu.regs[13]) == (12, 7, 4, 7)


def test_sum_array_same_result_with_and_without_forwarding():
    a = run(load("sum_array.asm"), forwarding=True)
    b = run(load("sum_array.asm"), forwarding=False)
    addr = load("sum_array.asm").data_labels["result"]
    assert a.dmem[addr] == b.dmem[addr] == 31
    assert a.stats.cycles < b.stats.cycles


def test_zero_register_is_immutable():
    cpu = run("li $zero, 99\n add $t0, $zero, $zero\n halt")
    assert cpu.regs[0] == 0 and cpu.regs[8] == 0


# ---------------- hazards & timing ----------------
def test_no_stalls_when_independent():
    cpu = run("li $t0,1\n li $t1,2\n li $t2,3\n li $t3,4\n halt")
    assert cpu.stats.data_stalls == 0
    assert cpu.stats.cycles == cpu.stats.retired + 4


def test_forwarding_removes_alu_stalls():
    cpu = run("li $t0,1\n add $t1,$t0,$t0\n add $t2,$t1,$t1\n halt", forwarding=True)
    assert cpu.stats.data_stalls == 0


def test_load_use_costs_one_stall_with_forwarding():
    cpu = run(".data\nx: .word 7\n.text\n lw $t0, 0($zero)\n add $t1,$t0,$t0\n halt", forwarding=True)
    assert cpu.stats.data_stalls == 1 and cpu.regs[9] == 14


def test_no_forwarding_back_to_back_costs_two_stalls():
    cpu = run("li $t0,1\n add $t1,$t0,$t0\n halt", forwarding=False)
    assert cpu.stats.data_stalls == 2


def test_taken_branch_penalty_is_two_cycles():
    cpu = run("beq $zero,$zero,end\n li $t0,1\n li $t1,2\nend: halt")
    assert cpu.stats.branch_penalty == 2
    assert cpu.regs[8] == 0 and cpu.regs[9] == 0      # wrong-path instrs squashed


def test_not_taken_branch_is_free():
    cpu = run("li $t0,1\n beq $t0,$zero,end\n li $t1,5\nend: halt")
    assert cpu.stats.branch_penalty == 0 and cpu.regs[9] == 5


@pytest.mark.parametrize("fwd", [True, False])
def test_cycle_accounting_identity(fwd):
    """cycles = retired + 4 (pipeline fill) + stalls + control penalties."""
    cpu = run(load("sum_array.asm"), forwarding=fwd)
    s = cpu.stats
    assert s.cycles == s.retired + 4 + s.data_stalls + s.branch_penalty


# ---------------- cache ----------------
def test_sequential_hit_rate_is_three_quarters():
    c = Cache(size=256, block=16, assoc=1)
    for i in range(64):
        c.access(4 * i)
    assert c.hit_rate == pytest.approx(0.75)


def test_conflict_misses_direct_mapped_vs_2way():
    a, b = 0, 256                       # same set in a 256 B direct-mapped cache
    dm, tw = Cache(256, 16, 1), Cache(256, 16, 2)
    for _ in range(10):
        for addr in (a, b):
            dm.access(addr)
            tw.access(addr)
    assert dm.hits == 0
    assert tw.hits == 18


def test_dirty_eviction_causes_writeback():
    c = Cache(32, 16, 1)                # 2 sets
    c.access(0, write=True)
    extra = c.access(32)                # same set, evicts dirty block
    assert c.writebacks == 1 and extra == 2 * c.miss_penalty


def test_cpu_with_cache_pays_miss_penalty():
    prog = load("matrix_walk.asm")
    base = run(prog)
    cached = run(prog, cache=Cache(256, 16, 1, miss_penalty=10))
    assert cached.stats.mem_stall_cycles == 10 * cached.cache.misses
    assert cached.stats.cycles == base.stats.cycles + cached.stats.mem_stall_cycles
