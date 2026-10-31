"""Cycle-accurate 5-stage (IF, ID, EX, MEM, WB) pipelined CPU model.

Design choices (classic Hennessy & Patterson textbook pipeline):
  * Register file writes in the first half of a cycle, reads in the second half,
    so a WB -> ID dependence never stalls.
  * Branches resolve in EX with a predict-not-taken policy (2-cycle penalty).
    Jumps resolve in ID (1-cycle penalty).
  * Forwarding (optional): EX/MEM -> EX and MEM/WB -> EX. Only load-use needs a stall.
  * Without forwarding the hazard unit stalls in ID until the producer reaches WB.
  * Optional data cache: a miss freezes the whole pipeline for the miss penalty.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .cache import Cache
from .isa import NOP, Instruction, Program

MASK = 0xFFFFFFFF


def s32(x: int) -> int:
    x &= MASK
    return x - (1 << 32) if x & 0x80000000 else x


class CPUError(RuntimeError):
    pass


@dataclass
class Latch:
    """A pipeline register. uid < 0 means a bubble."""
    instr: Instruction = NOP
    uid: int = -1
    pc: int = 0
    a: int = 0          # value of rs
    b: int = 0          # value of rt
    result: int = 0     # ALU result, or loaded value after MEM
    dest: Optional[int] = None

    @property
    def bubble(self) -> bool:
        return self.uid < 0


@dataclass
class Stats:
    cycles: int = 0
    retired: int = 0
    data_stalls: int = 0         # bubbles inserted by the hazard unit
    branch_penalty: int = 0      # cycles lost to taken branches / jumps
    mem_stall_cycles: int = 0    # cycles lost to cache misses
    branches: int = 0
    taken: int = 0

    @property
    def cpi(self) -> float:
        return self.cycles / self.retired if self.retired else 0.0


ALU_R = {
    "add": lambda a, b: a + b,
    "sub": lambda a, b: a - b,
    "and": lambda a, b: a & b,
    "or": lambda a, b: a | b,
    "slt": lambda a, b: int(a < b),
    "mul": lambda a, b: a * b,
}
ALU_I = {
    "addi": lambda a, i: a + i,
    "andi": lambda a, i: a & i,
    "ori": lambda a, i: a | i,
    "slti": lambda a, i: int(a < i),
}


class CPU:
    def __init__(self, program: Program, forwarding: bool = True,
                 cache: Optional[Cache] = None, max_cycles: int = 1_000_000):
        self.imem: List[Instruction] = program.instructions
        self.dmem: Dict[int, int] = dict(program.data)
        self.regs: List[int] = [0] * 32
        self.forwarding = forwarding
        self.cache = cache
        self.max_cycles = max_cycles

        self.pc = 0
        self.if_id = Latch()
        self.id_ex = Latch()
        self.ex_mem = Latch()
        self.mem_wb = Latch()

        self.cycle = 0
        self.halted = False
        self.fetch_stopped = False
        self.mem_stall = 0
        self._next_uid = 0
        self.stats = Stats()
        self.history: Dict[int, dict] = {}   # uid -> {"text", "stages": {cycle: name}, "flushed"}

    # ------------------------------------------------------------------ memory
    def _check(self, addr: int) -> None:
        if addr % 4:
            raise CPUError(f"unaligned memory access at address {addr}")
        if addr < 0:
            raise CPUError(f"negative memory address {addr}")

    def _load(self, addr: int) -> int:
        self._check(addr)
        if self.cache:
            self.mem_stall += self.cache.access(addr, write=False)
        return self.dmem.get(addr, 0)

    def _store(self, addr: int, value: int) -> None:
        self._check(addr)
        if self.cache:
            self.mem_stall += self.cache.access(addr, write=True)
        self.dmem[addr] = s32(value)

    # ------------------------------------------------------------ hazard logic
    def _forward(self, reg: Optional[int], value: int, ex_mem: Latch, mem_wb: Latch) -> int:
        if not reg:
            return value
        if not ex_mem.bubble and ex_mem.dest == reg and ex_mem.instr.op != "lw":
            return ex_mem.result
        if not mem_wb.bubble and mem_wb.dest == reg:
            return mem_wb.result
        return value

    def _must_stall(self, ins: Instruction, id_ex: Latch, ex_mem: Latch) -> bool:
        srcs = ins.sources
        if not srcs:
            return False
        if self.forwarding:   # only the load-use hazard remains
            return (not id_ex.bubble and id_ex.instr.op == "lw" and id_ex.instr.dest in srcs)
        return any(not l.bubble and l.instr.dest is not None and l.instr.dest in srcs
                   for l in (id_ex, ex_mem))

    # ---------------------------------------------------------------- tracing
    def _mark(self, latch: Latch, stage: str) -> None:
        if not latch.bubble:
            self.history[latch.uid]["stages"][self.cycle] = stage

    def _fetch(self) -> Latch:
        if self.fetch_stopped or not (0 <= self.pc < len(self.imem)):
            return Latch()
        ins = self.imem[self.pc]
        uid = self._next_uid
        self._next_uid += 1
        self.history[uid] = {"text": ins.text, "stages": {}, "flushed": False}
        latch = Latch(ins, uid, self.pc)
        self._mark(latch, "IF")
        self.pc += 1
        if ins.op == "halt":
            self.fetch_stopped = True
        return latch

    def _flush(self, latch: Latch) -> None:
        if not latch.bubble:
            self.history[latch.uid]["flushed"] = True

    # ------------------------------------------------------------------ cycle
    def step(self) -> None:
        self.cycle += 1
        st = self.stats
        st.cycles = self.cycle

        # A cache miss freezes the whole pipeline.
        if self.mem_stall > 0:
            self.mem_stall -= 1
            st.mem_stall_cycles += 1
            for latch, name in ((self.if_id, "IF"), (self.id_ex, "ID"),
                                (self.ex_mem, "EX"), (self.mem_wb, "MEM")):
                self._mark(latch, name)
            return

        old_if_id, old_id_ex = self.if_id, self.id_ex
        old_ex_mem, old_mem_wb = self.ex_mem, self.mem_wb
        for latch, name in ((old_if_id, "ID"), (old_id_ex, "EX"),
                            (old_ex_mem, "MEM"), (old_mem_wb, "WB")):
            self._mark(latch, name)

        # ---- WB ----
        wb = old_mem_wb
        if not wb.bubble:
            if wb.dest is not None:
                self.regs[wb.dest] = s32(wb.result)
            st.retired += 1
            if wb.instr.op == "halt":
                self.halted = True

        # ---- MEM ----
        m = old_ex_mem
        new_mem_wb = Latch(m.instr, m.uid, m.pc, result=m.result, dest=m.dest)
        if not m.bubble:
            if m.instr.op == "lw":
                new_mem_wb.result = self._load(m.result)
            elif m.instr.op == "sw":
                self._store(m.result, m.b)

        # ---- EX ----
        e = old_id_ex
        new_ex_mem = Latch()
        taken, target = False, 0
        if not e.bubble:
            ins = e.instr
            a, b = e.a, e.b
            if self.forwarding:
                a = self._forward(ins.rs, a, old_ex_mem, old_mem_wb)
                b = self._forward(ins.rt, b, old_ex_mem, old_mem_wb)
            result = 0
            if ins.op in ALU_R:
                result = ALU_R[ins.op](a, b)
            elif ins.op in ALU_I:
                result = ALU_I[ins.op](a, ins.imm)
            elif ins.op in ("lw", "sw"):
                result = a + ins.imm
            elif ins.op in ("beq", "bne"):
                st.branches += 1
                taken = (a == b) if ins.op == "beq" else (a != b)
                target = ins.target
                if taken:
                    st.taken += 1
            new_ex_mem = Latch(ins, e.uid, e.pc, a=a, b=b, result=s32(result), dest=ins.dest)

        # ---- ID ----
        d = old_if_id
        new_id_ex = Latch()
        stall = False
        jump_to: Optional[int] = None
        if taken:
            self._flush(d)                       # wrong-path instruction in ID
        elif not d.bubble:
            ins = d.instr
            if self._must_stall(ins, old_id_ex, old_ex_mem):
                stall = True
                st.data_stalls += 1
            else:
                a = self.regs[ins.rs] if ins.rs is not None else 0
                b = self.regs[ins.rt] if ins.rt is not None else 0
                new_id_ex = Latch(ins, d.uid, d.pc, a=a, b=b)
                if ins.op == "j":
                    jump_to = ins.target

        # ---- IF ----
        fetched = Latch() if stall else self._fetch()
        if taken:
            self._flush(fetched)
            new_if_id = Latch()
            self.pc, self.fetch_stopped = target, False
            st.branch_penalty += 2
        elif jump_to is not None:
            self._flush(fetched)
            new_if_id = Latch()
            self.pc, self.fetch_stopped = jump_to, False
            st.branch_penalty += 1
        elif stall:
            new_if_id = old_if_id                # hold the stalled instruction
        else:
            new_if_id = fetched

        self.if_id, self.id_ex, self.ex_mem, self.mem_wb = new_if_id, new_id_ex, new_ex_mem, new_mem_wb

        # Ran off the end of the program with an empty pipeline -> done.
        if (self.fetch_stopped or self.pc >= len(self.imem)) and all(
                l.bubble for l in (self.if_id, self.id_ex, self.ex_mem, self.mem_wb)):
            self.halted = True

    def run(self) -> Stats:
        while not self.halted:
            if self.cycle >= self.max_cycles:
                raise CPUError(f"exceeded max_cycles={self.max_cycles} (infinite loop?)")
            self.step()
        return self.stats

    # --------------------------------------------------------------- display
    def diagram(self, max_rows: int = 40, max_cols: int = 40) -> str:
        """Pipeline timing diagram. 'X*' means stage X is repeated (a stall)."""
        cols, w = min(self.cycle, max_cols), 5
        out = [f"{'instruction':<26}" + "".join(f"{c:<{w}}" for c in range(1, cols + 1))]
        for uid in sorted(self.history)[:max_rows]:
            h = self.history[uid]
            cells = []
            for c in range(1, cols + 1):
                s = h["stages"].get(c, "")
                if s and h["stages"].get(c - 1) == s:
                    s += "*"
                cells.append(f"{s:<{w}}")
            tail = "  <- flushed" if h["flushed"] else ""
            out.append(f"{h['text'][:24]:<26}" + "".join(cells) + tail)
        return "\n".join(out)
