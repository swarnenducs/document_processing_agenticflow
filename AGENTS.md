# Agent guidance

This repository contains independently deployable UI, API, MAF, document MCP, and voice MCP components.

This project was built with the microsoft-foundry skill. Before working on or answering questions about Foundry agents, read the microsoft-foundry skill first.

For Foundry-hosted MAF changes:

- Keep `central-agentic-flow` deployable as its existing FastAPI Web App.
- Keep deterministic API jobs on the Web App `POST /invoke` path.
- Use the Foundry Responses host only for conversational orchestration.
- Put document and voice MCP servers behind a Foundry Toolbox; never use localhost URLs in hosted deployments.
- Never commit `.env`, Azure keys, SAS tokens, project endpoints, or toolbox endpoints.
