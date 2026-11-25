# JARVIS project rules

- Target Windows 11 and Python 3.11.
- Bind servers to `127.0.0.1` only; never expose them to the network.
- Resolve paths with `pathlib` from the project root; never hardcode absolute paths.
- Log to `logs/jarvis.log`.
- Sensitive actions must go through an approval layer.
- Add a pytest test for each new Python module.
