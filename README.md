# PipeSim COA

A Python-based simulator for analyzing instruction pipelining, pipeline hazards, and processor performance in Computer Organization and Architecture (COA).

## 📌 Overview

**PipeSim COA** is an educational simulation tool designed to model the execution of instructions through a multi-stage CPU pipeline. It tracks instruction progression, identifies structural/data/control hazards, and calculates key architectural metrics like Clock Cycles Per Instruction (CPI) and speedup.

## 🚀 Features

* **Multi-Stage Pipeline Simulation:** Simulates key execution stages (IF, ID, EX, MEM, WB).
* **Hazard Detection:** Identifies data dependencies, stalls, and control hazards.
* **Performance Metrics:** Reports cycle counts, total executed instructions, and execution efficiency.

## 🛠️ Requirements & Setup

### Prerequisites
* **C Compiler:** `gcc` or `clang` installed on your system.

### Building the Project

1. Clone or download this repository:
   ```bash
   git clone [https://github.com/gaya3madathil-hash/pipesim-coa.git](https://github.com/gaya3madathil-hash/pipesim-coa.git)
   cd pipesim-coa
