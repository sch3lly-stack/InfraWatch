# Platform notes and limitations

The agent uses `psutil`, which supports Linux, macOS, Windows and the BSDs.

| Metric | Linux | macOS | Windows |
|---|---|---|---|
| CPU / memory / disk / network / uptime | yes | yes | yes |
| Load averages | yes | yes | **not available** (reported as null; UI shows "n/a") |
| Disk path | `/` default | `/` default | set `disk_path: 'C:\\'` |
| Process check | yes | yes | yes (name must match, e.g. `nginx.exe`) |

* Memory "available" follows psutil semantics (includes reclaimable cache on Linux; differs from macOS "free").
* Network throughput is the sum over all interfaces (including loopback) as a delta between collections; the first sample after start has no rate.
* Only one filesystem (`disk_path`) is reported per agent in this version.
* Containers: the agent reports the container's view of CPU/memory limits only where the kernel exposes them via psutil.
* Authoring/testing was done on macOS only; Linux and Windows are not yet covered by CI agent runs (the CI matrix covers Linux server/agent tests).
