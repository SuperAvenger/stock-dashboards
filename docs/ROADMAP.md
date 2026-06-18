# Roadmap

## Now

- Add deterministic tests around factor calculations and state-based notification deduplication.
- Version dashboard data contracts and display source freshness for each symbol.
- Separate data acquisition from scoring so providers can be replaced independently.

## Next

- Add benchmark-relative performance, factor explanations, and missing-data confidence flags.
- Expose read-only MCP tools for current scores, symbol comparisons, and factor explanations.
- Reuse the research metadata conventions from `quant_select` for reproducible results.

## Later

- Add user-defined watchlists and alert policies without storing brokerage credentials.
- Keep trade execution outside the dashboard service unless separately reviewed and secured.
