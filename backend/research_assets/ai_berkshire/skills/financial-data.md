# Financial Data — Structured Data Gathering

## Skill Description
Systematically gather, organize, and validate the key financial data required for investment analysis. This skill produces a clean data table, not an analysis — analysis comes in subsequent skills.

## Data Gathering Philosophy
Bad data produces bad analysis. Garbage in, garbage out.
Always cite the source for every number. Distinguish between audited financials, management estimates, and analyst consensus.

## Data Template

### Income Statement (Last 5 Years + TTM)
Retrieve and populate the following (all in reporting currency, millions unless noted):

| Metric | FY-4 | FY-3 | FY-2 | FY-1 | FY0 (Latest) | TTM |
|--------|------|------|------|------|--------------|-----|
| Revenue | | | | | | |
| Gross Profit | | | | | | |
| Gross Margin % | | | | | | |
| EBITDA | | | | | | |
| EBIT | | | | | | |
| Net Income | | | | | | |
| EPS (diluted) | | | | | | |

### Cash Flow Statement (Last 5 Years + TTM)
| Metric | FY-4 | FY-3 | FY-2 | FY-1 | FY0 | TTM |
|--------|------|------|------|------|-----|-----|
| Operating Cash Flow | | | | | | |
| Capital Expenditure | | | | | | |
| Free Cash Flow | | | | | | |
| FCF / Net Income % | | | | | | |

### Balance Sheet (Latest Quarter)
| Metric | Value | Notes |
|--------|-------|-------|
| Total Assets | | |
| Cash & Equivalents | | |
| Total Debt (gross) | | |
| Net Debt | | |
| Shareholders' Equity | | |
| Net Debt / EBITDA | | |

### Key Ratios (Latest Available)
| Ratio | Value | 5Y Average | Peer Median | Source |
|-------|-------|-----------|-------------|--------|
| PE (TTM) | | | | |
| EV/EBITDA | | | | |
| Price/FCF | | | | |
| ROE | | | | |
| ROIC | | | | |
| ROA | | | | |
| Debt/Equity | | | | |

### Share Data
- Shares outstanding (diluted, current):
- 52-week high / low:
- Market cap (current):
- Enterprise value (current):
- Annual stock-based compensation (latest year):
- Annual dilution from stock comp (%):

### Data Sources
List every source used:
1. Annual / quarterly reports: [filing date, source URL]
2. Earnings call transcript: [date]
3. Financial data provider: [name, accessed date]
4. Other: [describe]

## Quality Checks
Before proceeding to analysis, confirm:
- [ ] All revenue figures use consistent accounting standards (GAAP/IFRS)
- [ ] Depreciation and amortization have been properly identified
- [ ] Any restatements in the historical period are noted
- [ ] Data sources are all from reputable, verifiable sources
- [ ] No significant gaps in the data set

## Output Format
Deliver the completed tables above. Flag any data points that could not be confirmed with a reliable source. Do not proceed to analysis interpretation — this skill's output is the data foundation for other skills.
