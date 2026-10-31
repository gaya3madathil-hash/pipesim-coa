"""PipeSim: a 5-stage pipelined CPU + cache simulator for Computer Organisation & Architecture."""
from .isa import assemble, AsmError, Instruction, Program
from .cpu import CPU, Stats
from .cache import Cache

__all__ = ["assemble", "AsmError", "Instruction", "Program", "CPU", "Stats", "Cache"]
__version__ = "1.0.0"
