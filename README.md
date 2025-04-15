# ⚔️ Falyx

**Falyx** is a resilient, introspectable CLI framework for building robust, asynchronous command-line workflows with:

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
- Run in both interactive or headless (scriptable) modes
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
from falyx import Action, ChainedAction, Menu
from falyx.hooks import RetryHandler, log_success

async def flaky_step():
    import random, asyncio
    await asyncio.sleep(0.2)
    if random.random() < 0.8:
        raise RuntimeError("Random failure!")
    return "ok"

retry = RetryHandler()

step1 = Action("Step 1", flaky_step)
step1.hooks.register("on_error", retry.retry_on_error)

step2 = Action("Step 2", flaky_step)
step2.hooks.register("on_error", retry.retry_on_error)

chain = ChainedAction("My Pipeline", [step1, step2])
chain.hooks.register("on_success", log_success)

menu = Menu(title="🚀 Falyx Demo")
menu.add_command("R", "Run My Pipeline", chain)

if __name__ == "__main__":
    import asyncio
    asyncio.run(menu.run())
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

## 🧩 Components

| Component         | Purpose                                                |
|------------------|--------------------------------------------------------|
| `Action`          | Single async task with hook + result injection support |
| `ChainedAction`   | Sequential task runner with rollback                   |
| `ActionGroup`     | Parallel runner for independent tasks                  |
| `ProcessAction`   | CPU-bound task in a separate process (multiprocessing) |
| `Menu`            | CLI runner with toggleable prompt or headless mode     |
| `ExecutionContext`| Captures metadata per execution                        |
| `HookManager`     | Lifecycle hook registration engine                     |

---

## 🧠 Design Philosophy

> “Like a phalanx: organized, resilient, and reliable.”

Falyx is designed for developers who don’t just want CLI tools to run — they want them to **fail meaningfully**, **recover gracefully**, and **log clearly**.

---

## 🛣️ Roadmap

- [ ] Retry policy DSL (e.g., `max_retries=3, backoff="exponential"`)
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

