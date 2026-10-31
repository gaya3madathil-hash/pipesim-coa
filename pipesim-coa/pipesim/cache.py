"""Set-associative write-back / write-allocate cache with LRU replacement."""
from __future__ import annotations

import random
from collections import OrderedDict
from typing import Iterator


class Cache:
    def __init__(self, size: int = 256, block: int = 16, assoc: int = 1, miss_penalty: int = 10):
        if min(size, block, assoc, miss_penalty) <= 0:
            raise ValueError("cache parameters must be positive")
        if size % (block * assoc):
            raise ValueError("size must be a multiple of block * assoc")
        self.size, self.block, self.assoc, self.miss_penalty = size, block, assoc, miss_penalty
        self.num_sets = size // (block * assoc)
        self.sets = [OrderedDict() for _ in range(self.num_sets)]  # tag -> dirty (LRU first)
        self.hits = self.misses = self.writebacks = 0

    def access(self, addr: int, write: bool = False) -> int:
        """Access one address. Returns the *extra* stall cycles (0 on a hit)."""
        block_addr = addr // self.block
        idx = block_addr % self.num_sets
        tag = block_addr // self.num_sets
        s = self.sets[idx]
        if tag in s:
            s.move_to_end(tag)
            if write:
                s[tag] = True
            self.hits += 1
            return 0
        self.misses += 1
        extra = self.miss_penalty
        if len(s) >= self.assoc:
            _, dirty = s.popitem(last=False)      # evict LRU
            if dirty:
                self.writebacks += 1
                extra += self.miss_penalty        # write the dirty block back first
        s[tag] = write
        return extra

    @property
    def accesses(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return self.hits / self.accesses if self.accesses else 0.0

    def describe(self) -> str:
        kind = "direct-mapped" if self.assoc == 1 else f"{self.assoc}-way set-associative"
        return f"{self.size} B, {self.block} B blocks, {kind} ({self.num_sets} sets)"

    def summary(self) -> str:
        return (f"{self.accesses} accesses, {self.hits} hits, {self.misses} misses "
                f"({self.hit_rate:.1%} hit rate), {self.writebacks} writebacks")


def pattern_addresses(pattern: str, n: int, stride: int = 64, span: int = 65536,
                      working_set: int = 512, seed: int = 1) -> Iterator[int]:
    """Synthetic address streams for studying cache behaviour."""
    rng = random.Random(seed)
    for i in range(n):
        if pattern == "sequential":
            yield 4 * i
        elif pattern == "stride":
            yield (i * stride) % span
        elif pattern == "random":
            yield rng.randrange(0, span, 4)
        elif pattern == "loop":
            yield (4 * i) % working_set
        else:
            raise ValueError(f"unknown pattern '{pattern}'")
