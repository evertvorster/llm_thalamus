from __future__ import annotations

from datetime import datetime, timezone

from llm_thalamus.adapters.openmemory import client


def main() -> int:
    db_path = client.assert_db_present()

    # Read (must not throw; empty results OK)
    _ = client.search("the", k=1, user_id=client.get_default_user_id())

    # Write (throwaway OK)
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = f"PROBE openmemory write OK at {ts}"

    res = client.add(
        payload,
        user_id=client.get_default_user_id(),
        memory_type="semantic",
        metadata={"probe": True, "ts": ts, "source": "probe_openmemory_rw"},
        tags=["probe"],
    )

    # Try to extract an id if possible, then delete to keep DB tidy.
    mem_id = None
    if isinstance(res, dict):
        mem_id = res.get("id") or res.get("memory_id") or (res.get("data") or {}).get("id")

    if mem_id:
        try:
            client.delete(str(mem_id))
        except Exception:
            # delete is best-effort; write already proved the path works.
            pass

    print("probe_openmemory_rw: OK")
    print(f"  db_path={db_path}")
    print(f"  wrote={'yes' if res is not None else 'no'}")
    print(f"  deleted={'yes' if mem_id else 'no (no id)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
