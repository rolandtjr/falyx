# ⚔️ Falyx
![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Async-Ready](https://img.shields.io/badge/asyncio-ready-purple)

**Falyx** is a battle-ready, introspectable CLI framework for building resilient, asynchronous workflows with:

- ✅ Modular action chaining and rollback
- 🔁 Built-in retry handling
- ⚙️ Full lifecycle hooks (before, after, success, error, teardown)
- 📊 Execution tracing, logging, and introspection
- 🧙‍♂️ Async-first design with Process support
- 🧩 Extensible CLI menus and customizable output

> Built for developers who value *clarity*, *resilience*, and *visibility* in their terminal workflows.

---

## ✨ Why Falyx?

Modern CLI tools deserve the same resilience as production systems. Falyx makes it easy to:

- Compose workflows using `Action`, `ChainedAction`, or `ActionGroup`
- Inject the result of one step into the next (`last_result`)
- Handle flaky operations with retries and exponential backoff
- Roll back safely on failure with structured undo logic
- Add observability with execution timing, result tracking, and hooks
- Run in both interactive *and* headless (scriptable) modes
- Customize output with Rich `Table`s (grouping, theming, etc.)

---

## 🔧 Installation

```bash
pip install falyx
```

> Or install from source:

```bash
git clone https://github.com/rolandtjr/falyx.git
cd falyx
poetry install
```

---

## ⚡ Quick Example

```python
import asyncio
import random

from falyx import Falyx, Action, ChainedAction

# A flaky async step that fails randomly
async def flaky_step():
    await asyncio.sleep(0.2)
    if random.random() < 0.5:
        raise RuntimeError("Random failure!")
    return "ok"

# Create the actions
step1 = Action(name="step_1", action=flaky_step, retry=True)
step2 = Action(name="step_2", action=flaky_step, retry=True)

# Chain the actions
chain = ChainedAction(name="my_pipeline", actions=[step1, step2])

# Create the CLI menu
falyx = Falyx("🚀 Falyx Demo")
falyx.add_command(
    key="R",
    description="Run My Pipeline",
    action=chain,
    logging_hooks=True,
    # shows preview before confirmation
    preview_before_confirm=True,
    confirm=True,
)

# Entry point
if __name__ == "__main__":
    asyncio.run(falyx.run())
```

```bash
❯ python simple.py
                                🚀 Falyx Demo

  [R] Run My Pipeline
  [Y] History                                         [Q] Exit

>
```

```bash
❯ python simple.py run R
Command: 'R' — Run My Pipeline
└── ⛓ ChainedAction 'my_pipeline'
    ├── ⚙ Action 'step_1'
    │   ↻ Retries: 3x, delay 1.0s, backoff 2.0x
    └── ⚙ Action 'step_2'
        ↻ Retries: 3x, delay 1.0s, backoff 2.0x
Confirm execution of R — Run My Pipeline (calls `my_pipeline`)  [Y/n] y
[2025-04-15 22:03:57] WARNING   ⚠️ Retry attempt 1/3 failed due to 'Random failure!'.
✅ Result: ['ok', 'ok']
```

---

## 📦 Core Features

- ✅ Async-native `Action`, `ChainedAction`, `ActionGroup`
- 🔁 Retry policies + exponential backoff
- ⛓ Rollbacks on chained failures
- 🎛️ Headless or interactive CLI with argparse and prompt_toolkit
- 📊 Built-in execution registry, result tracking, and timing
- 🧠 Supports `ProcessAction` for CPU-bound workloads
- 🧩 Custom `Table` rendering for CLI menu views
- 🔍 Hook lifecycle: `before`, `on_success`, `on_error`, `after`, `on_teardown`

---

## 🔍 Execution Trace

```bash
[2025-04-14 10:33:22] DEBUG    [Step 1] ⚙ flaky_step()
[2025-04-14 10:33:22] INFO     [Step 1] 🔁 Retrying (1/3) in 1.0s...
[2025-04-14 10:33:23] DEBUG    [Step 1] ✅ Success | Result: ok
[2025-04-14 10:33:23] DEBUG    [My Pipeline] ✅ Result: ['ok', 'ok']
```

---

### 🧱 Core Building Blocks

#### `Action`
A single async unit of work. Can retry, roll back, or inject prior results.

#### `ChainedAction`
Run tasks in sequence. Supports rollback on failure and context propagation.

#### `ActionGroup`
Run tasks in parallel. Useful for fan-out operations like batch API calls.

#### `ProcessAction`
Offload CPU-bound work to another process — no extra code needed.

#### `Falyx`
Your CLI controller — powers menus, subcommands, history, bottom bars, and more.

#### `ExecutionContext`
Tracks metadata, arguments, timing, and results for each action execution.

#### `HookManager`
Registers and triggers lifecycle hooks (`before`, `after`, `on_error`, etc.) for actions and commands.

---

## 🧠 Design Philosophy

> “Like a phalanx: organized, resilient, and reliable.”

Falyx is designed for developers who don’t just want CLI tools to run — they want them to **fail meaningfully**, **recover gracefully**, and **log clearly**.

---

## 🛣️ Roadmap

- [ ] Metrics export (Prometheus-style)
- [ ] Plugin system for menu extensions
- [ ] Native support for structured logs + log forwarding
- [ ] Web UI for interactive execution history (maybe!)

---

## 🧑‍💼 License

MIT — use it, fork it, improve it. Attribution appreciated!

---

## 🌐 falyx.dev — **reliable actions, resilient flows**

---
