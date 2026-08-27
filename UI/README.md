# UI

Gradio display (`:7860`). Copy this folder to its own git. Talks to `ip_api` over HTTP only.

Tabs: Central Agent, Generate Document, Voice, Trace, **Admin** (templates + master data), **API targets** (JSON host switch).

Copy `config/ui_targets.example.json` behavior: in the UI, set `active_target` to `azure` and the Azure `api_base_url`, optionally `admin_api_key`, then Apply. Runtime file `config/ui_runtime.json` is gitignored.

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt   # pytest
cp .env.example .env
./run.sh
# or: python run.py
```
