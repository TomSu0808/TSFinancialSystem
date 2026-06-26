# AI Berkshire Skills (Vendored)

This directory contains vendored investment research skills from the
[xbtlin/ai-berkshire](https://github.com/xbtlin/ai-berkshire) project.

**Original source**: https://github.com/xbtlin/ai-berkshire  
**License**: MIT (see LICENSE file)  
**Vendored version**: Pinned for reproducibility — see upstream for latest.

## About AI Berkshire

AI Berkshire is a set of Claude Code skills that apply the combined investment
frameworks of Warren Buffett, Charlie Munger, Duan Yongping (段永平), and Li Lu (李录)
to systematic equity research.

## Skills

| File | Description |
|------|-------------|
| investment-research.md | Deep company analysis |
| investment-team.md | Multi-perspective investment team discussion |
| investment-checklist.md | Pre-investment checklist |
| portfolio-review.md | Portfolio-level review |
| thesis-tracker.md | Investment thesis tracking |
| news-pulse.md | News & event analysis |
| earnings-review.md | Earnings deep dive |
| earnings-team.md | Earnings team discussion |
| industry-research.md | Industry structure analysis |
| industry-funnel.md | Industry opportunity screening |
| quality-screen.md | Business quality assessment |
| management-deep-dive.md | Management quality analysis |
| financial-data.md | Financial data gathering |
| dyp-ask.md | Duan Yongping style questions |

## Usage in this platform

These skills are loaded by `backend/ai_berkshire_loader.py` and wrapped with
platform context (holdings, transactions) by `backend/research_prompt_builder.py`
before being submitted to an AI provider.

Attribution: *Research framework adapted from xbtlin/ai-berkshire, MIT License.*
