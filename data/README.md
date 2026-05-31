# Data drop point

The sender ships a bundle that looks like this:

```
bundle/
├── data/platform_*.jsonl    the actual data slice
├── schema.json              machine-readable schema + descriptions
├── SCHEMA.md                same, rendered for humans
├── RECEIVER.md              orientation doc
└── MANIFEST.json            file list + collection list
```

Place the **contents of the bundle** here so the layout becomes:

```
data/
├── platform_defectcode.jsonl
├── platform_lines.jsonl
├── platform_products.jsonl
├── platform_products_defect_history.jsonl
├── platform_products_steps.jsonl
├── platform_stations.jsonl
└── platform_workshifts.jsonl
```

The other files (`schema.json`, `SCHEMA.md`, `RECEIVER.md`, `MANIFEST.json`)
can sit at the repo root — they're for reference only and don't get imported.

Then run `mip import` (see top-level `README.md`).
