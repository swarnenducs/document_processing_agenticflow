# UI

Gradio display (`:7860`). Copy this folder to its own git. Talks to `ip_api` over HTTP only.

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt   # pytest
cp .env.example .env
./run.sh
# or: python run.py
```
