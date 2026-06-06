"""Interactive console helpers: toggle menu, prompts, navigation exceptions."""

from __future__ import annotations


class GoBack(Exception):
    """User requested to go back to the previous menu."""


class QuitSetup(Exception):
    """User requested to quit setup."""


def toggle_menu(title: str, items: list[str], selected: set[int],
                required_one: bool = False) -> set[int]:
    """Interactive toggle menu. Returns set of selected indices.

    Raises GoBack if user types 'b', QuitSetup if user types 'q'.
    """
    selected = set(selected)  # Copy to avoid mutating caller's data
    while True:
        print(f"\n=== {title} ===")
        for i, item in enumerate(items):
            mark = "X" if i in selected else " "
            print(f"  [{mark}] {i + 1}. {item}")
        raw = input("Toggle numbers, [b]ack, [q]uit, Enter=confirm: ").strip()
        if not raw:
            if required_one and not selected:
                print("  ⚠ At least one selection required.")
                continue
            return selected
        if raw.lower() in ("b", "back"):
            raise GoBack()
        if raw.lower() in ("q", "quit"):
            raise QuitSetup()
        for token in raw.split():
            try:
                idx = int(token) - 1
                if 0 <= idx < len(items):
                    selected ^= {idx}
            except ValueError:
                pass


def confirm(msg: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    raw = input(f"{msg} {suffix} ").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes")


def ask_int(msg: str, default: int) -> int:
    raw = input(f"{msg} [{default}]: ").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
