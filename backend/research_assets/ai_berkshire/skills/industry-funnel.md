# Industry Funnel — Opportunity Screening

## Skill Description
Systematically screen an industry to identify the most attractive investment candidates ranked by business quality and valuation. Output a prioritized watchlist with entry rationale.

## Screening Philosophy
Munger: "All I want to know is where I'm going to die, so I'll never go there." First filter out the businesses you will never own, then focus your time on the survivors.

## Funnel Stages

### Stage 1 — Industry Landscape Mapping
- List all publicly traded companies in the target industry (major markets)
- Classify by sub-segment within the industry
- Note approximate market cap range for each
- Initial size filter: apply minimum market cap threshold for liquidity (if applicable)

### Stage 2 — Quality Filter (Eliminate Low-Quality Businesses)
Apply these hard filters — any "fail" eliminates the candidate:

| Filter | Threshold | Pass / Fail |
|--------|-----------|-------------|
| ROIC (3-year average) | > 10% | |
| FCF positive | 3 of last 5 years | |
| Net debt / EBITDA | < 4× | |
| Revenue trend | Flat or growing | |
| Audit opinion | Clean / Unqualified | |

### Stage 3 — Moat Assessment
For companies passing Stage 2, rate the competitive advantage:
- **Grade A**: Wide moat — dominant position, pricing power, high switching costs
- **Grade B**: Narrow moat — some advantage but contestable
- **Grade C**: No moat — commodity player, price taker

Advance only Grade A and Grade B to Stage 4.

### Stage 4 — Valuation Screening
For remaining candidates, calculate:
- Current PE vs. 5-year average PE (premium / discount %)
- Current EV/EBITDA vs. 5-year average
- Current FCF yield
- Implied 5-year return at current price (base case)

Rank all candidates by expected risk-adjusted return.

### Stage 5 — Watchlist Output
Final output format:

| Rank | Company | Ticker | Market | Moat Grade | Est. Return | Entry Trigger | Priority |
|------|---------|--------|--------|------------|-------------|---------------|---------|
| 1 | | | | | | | |
| 2 | | | | | | | |
| 3 | | | | | | | |

For each top-3 candidate, provide 3 sentences: why the business is attractive, why the current valuation is interesting, and what specific event / price level would trigger serious research.

## Output Format
Complete all 5 stages. The watchlist must be actionable — include specific entry triggers, not vague "monitor" instructions.
