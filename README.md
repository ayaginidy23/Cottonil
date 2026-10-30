# Project documentation

Documentation of the Cottonil Data & AI Platform. It describes the methods, design and decisions.
It deliberately contains **no figures from the data**. Exact counts and results are in the
generated reports (`reports/`, kept locally and not pushed to GitHub).

| Document | What it covers |
|---|---|
| [architecture.md](architecture.md) | The big picture: components, database schemas, data flow, technology, run order |
| [data_pipeline.md](data_pipeline.md) | Bronze -> silver -> gold step by step: profiling, quality checks, investigations, cleaning decisions, reconciliation |
| [data_model.md](data_model.md) | Every gold table: grain, keys, important columns and how calculated columns are computed |
| [dashboards.md](dashboards.md) | The YAML app engine, the shared filters, and the 16 dashboards (KPIs, charts, what to look for) |
| [ai_assistants.md](ai_assistants.md) | Shopping Assistant and Business Analyst: how they work, tools, RAG, memory, photo and voice, security |
| [machine_learning.md](machine_learning.md) | Demand forecast method and evaluation, and the experiments that were not used and why |
| [data_limitations.md](data_limitations.md) | Known limits of the (partly generated) data and how the platform handles each one |

Reading order for a new person: architecture -> data_pipeline -> data_model -> dashboards -> ai_assistants.
