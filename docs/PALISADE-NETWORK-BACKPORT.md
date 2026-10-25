# SGSP networking backport — October 24, 2026

Backports the final networking/projection-startup changes from upstream SGSP while retaining the fork's Palisade controls and custom UI.

Included upstream work:
- 50fc142dd7eaec00417c16b5f8b12bec742de750: ENOSYS-only Bluetooth socket fallback. Already hotfixed on the device; now tracked on the feature branch with its tests.
- 44efc8d935084dba96b175bcfadd179c7caf5856: 60-second first-renderer-frame startup allowance; five-second post-start stall watchdog unchanged.
- 1ebbff5cd942b31065516bf2ee11afc7a9355014: final SCHED_IDLE renderer placement on background cores 0–2. The normal transport placement stays on core 6. Earlier intermediate scheduler experiments are not separately imported.

A full comparison found no additional unmerged differences in the Bluetooth bridge, core Bluetooth owner, Galaxy HTTP connection manager, companion backend or Android Auto Wi-Fi joining implementation. Their earlier ownership/network changes are already included.

Upstream projection map/widget/schema changes are UI work with dependencies on newer shared UI metadata. They are not part of this networking backport; directly copying those files would remove custom telemetry/neon integration and mismatch this fork's schema.

Validation: 30 upstream socket, renderer startup and placement tests passed against isolated candidate modules on the off-road comma; active files were not changed. Whitespace check passed. No native build, vehicle-control change, Panda firmware change, pairing operation or connection attempt was performed.

Deployment is separate: the active device remains base 77d7e6e with its earlier socket-only local hotfix. This source backport is not proof of MagicBox streaming or iOS failover compatibility. The last read-only status had no selected receiver and auto-connect manually paused; those are independent configuration blockers.
