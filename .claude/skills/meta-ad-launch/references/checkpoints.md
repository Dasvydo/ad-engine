# Checkpoints

Each checkpoint answers **one** question. Don't answer the day-7 question on day 1:
at DKK 35/day the early numbers are noise, and acting on noise restarts learning.

Pull the numbers with `ads_get_ad_entities` at `level: ad` for the launched ads
(and `level: adset` for the totals). Verify field names with
`ads_get_field_context` before first use.

| When | The question | Pull | Healthy | Act if |
|---|---|---|---|---|
| **+2h** | Did it get approved? | `effective_status` per ad, `ads_get_errors` | `ACTIVE` or `IN_PROCESS` | `DISAPPROVED` / `WITH_ISSUES` → quote the error, give the fix |
| **+24h** | Is it spending? | spend and impressions per ad, yesterday | spend is a real share of the daily budget, every ad has impressions | spend ≈ 0 → delivery is stuck: errors, account status, payment method |
| **Day 3** | Early shape only | spend, impressions, CPM by country, link clicks, link CTR per ad | - | **nothing.** Say it's noise and when the real read is |
| **Day 7** | The real read | CPC, CPM with the **country breakdown**, link CTR per ad, reach, frequency | CPC ≤ daily budget ÷ 10 (DKK 3.50 at 35/day) · link CTR 0.6-1.0% normal, >1.5% good | CTR < 0.5% → a creative problem · CPC > DKK 8 → the budget is undersized for the market |
| **Day 14** | The verdict | same as day 7, over 14 days | - | name a winner **only if the gap is ≥ 50%**, propose the next swap |

Why these lines:

- **Budget ÷ 10** is Meta's own rule of thumb: the daily budget should be at least 10×
  the cost per result.
- **The country breakdown** matters because LT is cheaper than DK. Meta skews delivery
  there, so a blended CPM quietly becomes Lithuania's.
- **A gap under ~50% between ads is noise.** Identical ad sets have been measured
  drifting 25% apart by chance alone.
- Bands for CTR, CPC and CPM are in `docs/META-ADS-CHEATSHEET.md`.

If the ad set targets the ~2,000-person custom audience instead of broad geo,
**frequency** is the primary metric: use `../meta-ads/references/operating-loop.md`.

## Report format - phone-first

```
📊 Day 7 · DoviLoop ads · 3 live
Spend DKK 241 / 245 budgeted
CPC DKK 2.90 ✅ (rule: ≤ 3.50)
CPM DKK 58 · LT 44 · DK 71 (LT 63% of impressions)
Link CTR · v3 1.2% · v4 0.8% · v2 0.7% - gap < 50%, noise
Site: not measured (no pixel on www.doviloop.dev)
Next: nothing to do. Next check day 14.
```

- **Every number comes from a tool result in this session.** If one wasn't returned,
  write "not returned". A missing value and a zero are different facts.
- One line of "Next:", and it is usually "nothing".
- No causes you can't see in the data.

## Don't touch - the first 14 days

Each of these restarts Meta's learning, and at this budget learning never finishes:

- adding an ad (swap instead, and only on his instruction)
- pausing the "losing" ad (you'd most likely be cutting noise)
- a targeting change
- moving the budget more than 20%
