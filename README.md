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
- 🧩 Extensible CLI menus, customizable bottom bars, and keyboard shortcuts

> Built for developers who value *clarity*, *resilience*, and *visibility* in their terminal workflows.

---

## ✨ Why Falyx?

Modern CLI tools deserve the same resilience as production systems. Falyx makes it easy to:

- Compose workflows using `Action`, `ChainedAction`, or `ActionGroup`
- Inject the result of one step into the next (`last_result` / `auto_inject`)
- Handle flaky operations with retries, backoff, and jitter
- Roll back safely on failure with structured undo logic
- Add observability with timing, tracebacks, and lifecycle hooks
- Run in both interactive *and* headless (scriptable) modes
- Support config-driven workflows with YAML or TOML
- Visualize tagged command groups and menu state via Rich tables

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

from falyx import Falyx
from falyx.action import Action, ChainedAction

# A flaky async step that fails randomly
async def flaky_step():
    await asyncio.sleep(0.2)
    if random.random() < 0.5:
        raise RuntimeError("Random failure!")
    print("ok")
    return "ok"

# Create the actions
step1 = Action(name="step_1", action=flaky_step)
step2 = Action(name="step_2", action=flaky_step)

# Chain the actions
chain = ChainedAction(name="my_pipeline", actions=[step1, step2])

# Create the CLI menu
falyx = Falyx("🚀 Falyx Demo")
falyx.add_command(
    key="R",
    description="Run My Pipeline",
    action=chain,
    preview_before_confirm=True,
    confirm=True,
    retry_all=True,
    spinner=True,
    style="cyan",
)

# Entry point
if __name__ == "__main__":
    asyncio.run(falyx.run())
```

```bash
$ python simple.py
                          🚀 Falyx Demo

           [R] Run My Pipeline
           [H] Help              [Y] History   [X] Exit

>
```

```bash
$ python simple.py run r
Command: 'R' — Run My Pipeline
└── ⛓ ChainedAction 'my_pipeline'
    ├── ⚙ Action 'step_1'
    │   ↻ Retries: 3x, delay 1.0s, backoff 2.0x
    └── ⚙ Action 'step_2'
        ↻ Retries: 3x, delay 1.0s, backoff 2.0x
❓ Confirm execution of R — Run My Pipeline (calls `my_pipeline`)  [Y/n] > y
[2025-07-20 09:29:35] WARNING   Retry attempt 1/3 failed due to 'Random failure!'.
ok
[2025-07-20 09:29:38] WARNING   Retry attempt 1/3 failed due to 'Random failure!'.
ok
```

---

## 📦 Core Features

- ✅ Async-native `Action`, `ChainedAction`, `ActionGroup`, `ProcessAction`
- 🔁 Retry policies with delay, backoff, jitter — opt-in per action or globally
- ⛓ Rollbacks and lifecycle hooks for chained execution
- 🎛️ Headless or interactive CLI powered by `argparse` + `prompt_toolkit`
- 📊 In-memory `ExecutionRegistry` with result tracking, timing, and tracebacks
- 🌐 CLI menu construction via config files or Python
- ⚡ Bottom bar toggle switches and counters with `Ctrl+<key>` shortcuts
- 🔍 Structured confirmation prompts and help rendering
- 🪵 Flexible logging: Rich console for devs, JSON logs for ops

---

### 🧰 Building Blocks

- **`Action`**: A single unit of async (or sync) logic
- **`ChainedAction`**: Execute a sequence of actions, with rollback and injection
- **`ActionGroup`**: Run actions concurrently and collect results
- **`ProcessAction`**: Use `multiprocessing` for CPU-bound workflows
- **`Falyx`**: Interactive or headless CLI controller with history, menus, and theming
- **`ExecutionContext`**: Metadata store per invocation (name, args, result, timing)
- **`HookManager`**: Attach `before`, `after`, `on_success`, `on_error`, `on_teardown`

---

### 🔍 Logging
```
2025-07-20 09:29:32 [falyx] [INFO] Command 'R' selected.
2025-07-20 09:29:32 [falyx] [INFO] [run_key] Executing: R — Run My Pipeline
2025-07-20 09:29:33 [falyx] [INFO] [my_pipeline] Starting -> ChainedAction(name=my_pipeline, actions=['step_1', 'step_2'], args=(), kwargs={}, auto_inject=False, return_list=False)()
2025-07-20 09:29:33 [falyx] [INFO] [step_1] Retrying (1/3) in 1.0s due to 'Random failure!'...
2025-07-20 09:29:35 [falyx] [WARNING] [step_1] Retry attempt 1/3 failed due to 'Random failure!'.
2025-07-20 09:29:35 [falyx] [INFO] [step_1] Retrying (2/3) in 2.0s due to 'Random failure!'...
2025-07-20 09:29:37 [falyx] [INFO] [step_1] Retry succeeded on attempt 2.
2025-07-20 09:29:37 [falyx] [INFO] [step_1] Recovered: step_1
2025-07-20 09:29:37 [falyx] [DEBUG] [step_1] status=OK duration=3.627s result='ok' exception=None
2025-07-20 09:29:37 [falyx] [INFO] [step_2] Retrying (1/3) in 1.0s due to 'Random failure!'...
2025-07-20 09:29:38 [falyx] [WARNING] [step_2] Retry attempt 1/3 failed due to 'Random failure!'.
2025-07-20 09:29:38 [falyx] [INFO] [step_2] Retrying (2/3) in 2.0s due to 'Random failure!'...
2025-07-20 09:29:40 [falyx] [INFO] [step_2] Retry succeeded on attempt 2.
2025-07-20 09:29:40 [falyx] [INFO] [step_2] Recovered: step_2
2025-07-20 09:29:40 [falyx] [DEBUG] [step_2] status=OK duration=3.609s result='ok' exception=None
2025-07-20 09:29:40 [falyx] [DEBUG] [my_pipeline] Success -> Result: 'ok'
2025-07-20 09:29:40 [falyx] [DEBUG] [my_pipeline] Finished in 7.237s
2025-07-20 09:29:40 [falyx] [DEBUG] [my_pipeline] status=OK duration=7.237s result='ok' exception=None
2025-07-20 09:29:40 [falyx] [DEBUG] [Run My Pipeline] status=OK duration=7.238s result='ok' exception=None
```

### 📊 History Tracking

View full execution history:

```bash
> history
                                                   📊 Execution History

   Index   Name                           Start         End    Duration   Status        Result / Exception
 ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
       0   step_1                      09:23:55    09:23:55      0.201s   ✅ Success    'ok'
       1   step_2                      09:23:55    09:24:03      7.829s   ❌ Error      RuntimeError('Random failure!')
       2   my_pipeline                 09:23:55    09:24:03      8.080s   ❌ Error      RuntimeError('Random failure!')
       3   Run My Pipeline             09:23:55    09:24:03      8.082s   ❌ Error      RuntimeError('Random failure!')
```

Inspect result by index:

```bash
> history --result-index 0
Action(name='step_1', action=flaky_step, args=(), kwargs={}, retry=True, rollback=False) ():
ok
```

Print last result includes tracebacks:

```bash
> history --last-result
Command(key='R', description='Run My Pipeline' action='ChainedAction(name=my_pipeline, actions=['step_1', 'step_2'],
args=(), kwargs={}, auto_inject=False, return_list=False)') ():
Traceback (most recent call last):
  File ".../falyx/command.py", line 291, in __call__
    result = await self.action(*combined_args, **combined_kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File ".../falyx/action/base_action.py", line 91, in __call__
    return await self._run(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File ".../falyx/action/chained_action.py", line 212, in _run
    result = await prepared(*combined_args, **updated_kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File ".../falyx/action/base_action.py", line 91, in __call__
    return await self._run(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File ".../falyx/action/action.py", line 157, in _run
    result = await self.action(*combined_args, **combined_kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File ".../falyx/examples/simple.py", line 15, in flaky_step
    raise RuntimeError("Random failure!")
RuntimeError: Random failure!
```

---

## 🧠 Design Philosophy

> “Like a phalanx: organized, resilient, and reliable.”

Falyx is designed for developers who don’t just want CLI tools to run — they want them to **fail meaningfully**, **recover intentionally**, and **log clearly**.

---
