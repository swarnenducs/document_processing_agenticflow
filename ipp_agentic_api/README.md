# ipp_agentic_api

FastAPI gateway (`:8000`). Copy this folder to its own git. Talks to MAF over HTTP only.

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt   # pytest
cp .env.example .env
./run.sh
# or: python run.py
```

`run.py` starts this API. The monorepo stack launcher remains `python run_all_components.py` at the workspace root.
