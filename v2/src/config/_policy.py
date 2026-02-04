from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Roots:
    mode: str  # "dev" or "installed"
    project_root: Path

    resources_root: Path

    # NEW: separate template vs active config file
    config_template: Path
    config_file: Path

    runtime_root: Path
    data_root: Path
    state_root: Path


def compute_roots_for_mode(*, mode: str, project_root: Path, create_dirs: bool = True) -> Roots:
    """
    Canonical path policy for config + runtime roots.

    Dev mode:
      resources_root:   <repo>/resources
      config_template:  <repo>/resources/config/config.json
      config_file:      <repo>/resources/config/config.json   (same file in dev)
      runtime_root:     <repo>/var/llm-thalamus-dev
      data_root:        <repo>/var/llm-thalamus-dev/data
      state_root:       <repo>/var/llm-thalamus-dev/state

    Installed mode:
      resources_root:   /usr/share/llm-thalamus
      config_template:  /usr/share/llm-thalamus/config/config.json   (read-only)
      config_file:      ~/.config/llm-thalamus/config.json           (user-owned, active)
      data_root:        ~/.local/share/llm-thalamus
      state_root:       ~/.local/state/llm-thalamus
    """
    project_root = project_root.resolve()

    if mode == "dev":
        resources_root = project_root / "resources"

        config_template = resources_root / "config" / "config.json"
        config_file = config_template  # dev uses the shipped file directly

        runtime_root = project_root / "var" / "llm-thalamus-dev"
        data_root = runtime_root / "data"
        state_root = runtime_root / "state"

        if create_dirs:
            data_root.mkdir(parents=True, exist_ok=True)
            state_root.mkdir(parents=True, exist_ok=True)

    elif mode == "installed":
        resources_root = Path("/usr/share/llm-thalamus")

        config_template = resources_root / "config" / "config.json"

        config_root = Path.home() / ".config" / "llm-thalamus"
        config_file = config_root / "config.json"

        data_root = Path.home() / ".local" / "share" / "llm-thalamus"
        state_root = Path.home() / ".local" / "state" / "llm-thalamus"
        runtime_root = state_root

        # No mkdir here by default; creation should be explicit in the loader step
        # so summaries don’t cause side-effects.

    else:
        raise ValueError(f"Unknown mode: {mode!r}")

    return Roots(
        mode=mode,
        project_root=project_root,
        resources_root=resources_root,
        config_template=config_template,
        config_file=config_file,
        runtime_root=runtime_root,
        data_root=data_root,
        state_root=state_root,
    )


def resolve_resource_path(resources_root: Path, value: str) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    return (resources_root / p).resolve()


def resolve_writable_path(base_root: Path, value: str) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    if value.startswith("./"):
        p = Path(value[2:])
    return (base_root / p).resolve()


def format_mode_summary(*, dev_roots, dev_effective, inst_roots, inst_effective) -> str:
    lines: list[str] = []
    lines.append("== resolved paths comparison ==")
    lines.append("")

    def block(title: str, roots, eff) -> None:
        lines.append(f"[{title}]")
        lines.append(f"resources_root:   {roots.resources_root}")
        lines.append(f"config_template:  {roots.config_template}")
        lines.append(f"config_file:      {roots.config_file}")
        lines.append(f"data_root:        {roots.data_root}")
        lines.append(f"state_root:       {roots.state_root}")
        lines.append("")
        lines.append(f"openmemory_db:    {eff.openmemory_db_path}")
        lines.append(f"log_file:         {eff.log_file}")
        lines.append(f"message_file:     {eff.message_file}")
        lines.append("prompt_files:")
        for name, p in sorted(eff.prompt_files.items()):
            lines.append(f"  {name:14} {p}")
        lines.append("")

    block("dev", dev_roots, dev_effective)
    block("installed", inst_roots, inst_effective)

    return "\n".join(lines)
