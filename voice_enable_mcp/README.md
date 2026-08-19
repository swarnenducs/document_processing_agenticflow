# voice_enable_mcp

Voice / contract LangGraph as FastMCP (`:8002`). Copy this folder to its own git.

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt   # pytest
cp .env.example .env
./run.sh
# or: python run.py --transport http --host 127.0.0.1 --port 8002
```
