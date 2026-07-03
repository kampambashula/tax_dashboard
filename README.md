# Zambia MTRS Executive Dashboard

## Run locally
```
pip install -r requirements.txt
streamlit run app.py
```

The app reads `data/data.xls` (the ZRA/MOF statistical bulletin, saved as a
tab-separated file with an .xls extension) directly — no manual conversion
needed. Replace that file with a future edition of the bulletin (same table
order) and the dashboard will re-classify and re-render automatically.

## What it contains
- Executive KPI cards (tax revenue, % of GDP, tax-head collections, cost of
  collection, trade values, registered importers/exporters)
- Revenue Performance (nominal collections by tax head, % of GDP trends,
  public vs private sector contribution)
- Taxpayer Segments (Large / Medium / Small contribution, government funding)
- Administration & Compliance (cost of collection, e-payment vs cash share,
  VAT refunds, mining vs non-mining refund distribution)
- Customs & Trade Summary (imports vs exports, trade balance, registered
  traders, customs entries, value for duty purposes)
- Trade by Commodity (HS-section-level imports/exports, top-N ranking + trend)
- Trading Partners (ranked import/export partners, top-N + trend)
- Border Posts (export/import value, re-exports, re-imports by post)
- Data & Download tab with a column dictionary and CSV export

All figures are exactly as reported in the uploaded workbook — nothing is
invented or estimated.
