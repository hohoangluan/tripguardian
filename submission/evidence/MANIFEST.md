# Bằng chứng số liệu

Sinh bằng `python3 submission/tools/collect_evidence.py`. `data/` không nằm trong repo (dung lượng, review của người thật); đây là bản sao các file tổng hợp mà báo cáo trích. Toàn bộ dữ liệu: gói Drive trong `README.md`.

| File | Byte | Sửa lần cuối (nguồn) | sha256 (16 ký tự đầu) | Lệnh sinh lại |
|---|---|---|---|---|
| `data/decision/eval.json` | 35,451 | 2026-10-09 06:26 UTC | `7e8d9422cafa1694` | `python -m decision evaluate` |
| `data/planning/eval.json` | 2,128 | 2026-10-03 08:33 UTC | `2d516eac800dac81` | `python -m planning evaluate` |
| `data/journey_sim/report.json` | 32,818 | 2026-10-10 09:05 UTC | `f696226211d2ebbd` | `python scripts/journey_sim.py` |
| `data/bench/offline-20261007/summary.csv` | 976 | 2026-10-07 17:12 UTC | `77ffcc55a2c605ca` | `python -m bench run` |
| `data/bench/offline-20261007/runs.csv` | 15,806 | 2026-10-07 17:12 UTC | `a33373e189149006` | `python -m bench run` |
| `data/bench/offline-20261007/fields.csv` | 80,819 | 2026-10-07 17:12 UTC | `f4eb930b4bf177e8` | `python -m bench run` |
| `data/bench/live-20261007/summary.csv` | 926 | 2026-10-07 16:54 UTC | `c032ceea2cdde99b` | `python -m bench run --live` |
| `data/bench/live-20261007/runs.csv` | 12,420 | 2026-10-07 16:54 UTC | `04dd067f857e36d3` | `python -m bench run --live` |
| `data/bench/live-20261007/fields.csv` | 14,432 | 2026-10-07 16:54 UTC | `80ec4d676dbe6f86` | `python -m bench run --live` |
| `data/intel/summary.json` | 550 | 2026-10-08 03:40 UTC | `9ca30e6a5fecd18f` | `python -m corpus aggregate` |
| `data/gmaps/observe_summary.json` | 2,728 | 2026-10-09 07:00 UTC | `484292c256c5878b` | `python -m corpus build (observe step)` |

`counts.json`: số địa điểm theo từng tầng (serving, intel, snapshot web) và số nhãn Judge, đếm từ file gốc.
