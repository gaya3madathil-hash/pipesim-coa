"""A tiny MIPS-like ISA and a two-pass assembler."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

NAMES = (
    ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3"]
    + [f"t{i}" for i in range(8)]
    + [f"s{i}" for i in range(8)]
    + ["t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]
)
REG_NUM = {n: i for i, n in enumerate(NAMES)}

R_OPS = {"add", "sub", "and", "or", "slt", "mul"}
I_OPS = {"addi", "andi", "ori", "slti"}


class AsmError(Exception):
    """Raised for any assembly-time error (message includes the line number)."""


@dataclass(frozen=True)
class Instruction:
    op: str
    rd: Optional[int] = None      # destination register (writing ops only)
    rs: Optional[int] = None      # first source / base register
    rt: Optional[int] = None      # second source / store-data register
    imm: int = 0
    target: int = 0               # absolute instruction index (branch / jump)
    text: str = "nop"

    @property
    def sources(self) -> Tuple[int, ...]:
        """Source registers that matter for hazards ($zero never creates one)."""
        return tuple(r for r in (self.rs, self.rt) if r)

    @property
    def dest(self) -> Optional[int]:
        """Destination register, or None if the instruction writes nothing."""
        return self.rd if self.rd else None


NOP = Instruction("nop", text="nop")


@dataclass
class Program:
    instructions: List[Instruction] = field(default_factory=list)
    data: Dict[int, int] = field(default_factory=dict)     # byte address -> word
    labels: Dict[str, int] = field(default_factory=dict)   # text label -> instr index
    data_labels: Dict[str, int] = field(default_factory=dict)


def parse_reg(tok: str, lineno: int) -> int:
    t = tok.strip().lstrip("$").lower()
    if t in REG_NUM:
        return REG_NUM[t]
    m = re.fullmatch(r"r?(\d+)", t)
    if m and 0 <= int(m.group(1)) < 32:
        return int(m.group(1))
    raise AsmError(f"line {lineno}: unknown register '{tok.strip()}'")


def _imm(tok: str, lineno: int, data_labels: Dict[str, int]) -> int:
    tok = tok.strip()
    try:
        return int(tok, 0)
    except ValueError:
        pass
    if tok in data_labels:
        return data_labels[tok]
    raise AsmError(f"line {lineno}: bad immediate or unknown data label '{tok}'")


_MEM_RE = re.compile(r"^(.*)\((.+)\)$")


def _mem(tok: str, lineno: int, data_labels: Dict[str, int]) -> Tuple[int, int]:
    m = _MEM_RE.match(tok.strip())
    if not m:
        raise AsmError(f"line {lineno}: expected offset(base), got '{tok.strip()}'")
    return _imm(m.group(1).strip() or "0", lineno, data_labels), parse_reg(m.group(2), lineno)


def assemble(source: str) -> Program:
    """Assemble source text into a Program. Supports .data/.text, .word, .space,
    labels, comments (# or ;) and the pseudo-ops li, la, move."""
    # ---- pass 1: strip, collect labels, lay out data ----
    section = "text"
    items: List[Tuple[int, str]] = []
    labels: Dict[str, int] = {}
    data_labels: Dict[str, int] = {}
    data: Dict[int, int] = {}
    daddr = 0

    for lineno, raw in enumerate(source.splitlines(), 1):
        line = re.split(r"[#;]", raw, maxsplit=1)[0].strip()
        while True:
            m = re.match(r"^([A-Za-z_]\w*)\s*:\s*(.*)$", line)
            if not m:
                break
            name, line = m.group(1), m.group(2).strip()
            if name in labels or name in data_labels:
                raise AsmError(f"line {lineno}: duplicate label '{name}'")
            if section == "text":
                labels[name] = len(items)
            else:
                data_labels[name] = daddr
        if not line:
            continue
        if line.startswith("."):
            parts = line.split(None, 1)
            d = parts[0].lower()
            if d == ".data":
                section = "data"
            elif d == ".text":
                section = "text"
            elif d == ".word" and section == "data":
                for v in (parts[1].split(",") if len(parts) > 1 else []):
                    try:
                        data[daddr] = int(v.strip(), 0)
                    except ValueError:
                        raise AsmError(f"line {lineno}: bad .word value '{v.strip()}'")
                    daddr += 4
            elif d == ".space" and section == "data":
                try:
                    daddr += 4 * int(parts[1].strip(), 0)
                except (IndexError, ValueError):
                    raise AsmError(f"line {lineno}: .space needs a word count")
            else:
                raise AsmError(f"line {lineno}: unsupported directive '{d}' in {section} section")
            continue
        if section != "text":
            raise AsmError(f"line {lineno}: instruction in .data section")
        items.append((lineno, line))

    # ---- pass 2: encode ----
    prog = Program(data=data, labels=labels, data_labels=data_labels)

    for idx, (lineno, line) in enumerate(items):
        parts = line.split(None, 1)
        op = parts[0].lower()
        args = [a.strip() for a in parts[1].split(",")] if len(parts) > 1 else []

        def need(n: int) -> None:
            if len(args) != n:
                raise AsmError(f"line {lineno}: '{op}' expects {n} operand(s), got {len(args)}")

        def label(name: str) -> int:
            if name not in labels:
                raise AsmError(f"line {lineno}: unknown label '{name}'")
            return labels[name]

        R = lambda t: parse_reg(t, lineno)
        if op in ("nop", "halt"):
            need(0)
            ins = Instruction(op, text=line)
        elif op in ("li", "la"):
            need(2)
            ins = Instruction("addi", rd=R(args[0]), rs=0, imm=_imm(args[1], lineno, data_labels), text=line)
        elif op == "move":
            need(2)
            ins = Instruction("add", rd=R(args[0]), rs=R(args[1]), rt=0, text=line)
        elif op in R_OPS:
            need(3)
            ins = Instruction(op, rd=R(args[0]), rs=R(args[1]), rt=R(args[2]), text=line)
        elif op in I_OPS:
            need(3)
            ins = Instruction(op, rd=R(args[0]), rs=R(args[1]), imm=_imm(args[2], lineno, data_labels), text=line)
        elif op == "lw":
            need(2)
            off, base = _mem(args[1], lineno, data_labels)
            ins = Instruction("lw", rd=R(args[0]), rs=base, imm=off, text=line)
        elif op == "sw":
            need(2)
            off, base = _mem(args[1], lineno, data_labels)
            ins = Instruction("sw", rt=R(args[0]), rs=base, imm=off, text=line)
        elif op in ("beq", "bne"):
            need(3)
            ins = Instruction(op, rs=R(args[0]), rt=R(args[1]), target=label(args[2]), text=line)
        elif op == "j":
            need(1)
            ins = Instruction("j", target=label(args[0]), text=line)
        else:
            raise AsmError(f"line {lineno}: unknown instruction '{op}'")
        prog.instructions.append(ins)

    return prog
