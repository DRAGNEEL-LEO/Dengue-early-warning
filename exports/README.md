# Sample dispatch exports

Generated offline by `python generate_exports.py` (defaults: data up to the week of 2024-08-12, 4-week horizon,
60% regional stock, 40 spraying crews, priority-weighted policy, expected demand). `scenario.json` records the
exact settings and totals.

| File | Content |
|---|---|
| `sample_sms.txt` | SMS notices for contrasting wards (overflow sender, receiver, top / lowest priority) |
| `sample_whatsapp.txt` | The same notices formatted for WhatsApp |
| `sample_commissioner_brief.html` | Printable city brief, one card per ward in priority order |
| `sample_commissioner_brief.pdf` | The same brief as PDF |
| `dispatch_plan_all_wards.csv` | Full 60-ward plan: forecast, priority, required / allocated / deficit, crews, routing |
| `bed_transfers.csv` | Intra-city patient transfers (from ward, to ward, patients) |
| `city_bed_utilization.csv` | City bed demand, capacity, utilisation before and after routing, unplaced patients |
| `simulator_roi_ranking.csv` | Simulator output for 20 optimised crews, ranked by cases prevented per crew |
| `offline_check_report.txt` | Latest result of `python offline_check.py` (network disabled) |

Bed capacities are demo assumptions and intervention effects are simulated scenarios; see the main README.
