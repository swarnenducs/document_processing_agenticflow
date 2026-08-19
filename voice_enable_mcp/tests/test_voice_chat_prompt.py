"""Voice YAML prompts load as LangChain ChatPromptTemplate / LCEL."""

from __future__ import annotations

from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from voice_enable_mcp.services.prompts import build_confirm_chain, build_intent_chain
from voice_enable_mcp.services.voice_lcel import VoiceIntentPayload, parse_voice_transcript


def test_chat_prompt_from_yaml(tmp_path: Path, monkeypatch) -> None:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "sample.yml").write_text(
        "name: sample\nsystem: |\n  You are a helper.\nhuman: |\n  User said: {transcript}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VOICE_PROMPTS_DIR", str(prompts))

    from voice_enable_mcp.prompts_loader import chat_prompt_from_yaml

    prompt = chat_prompt_from_yaml("sample.yml")
    assert isinstance(prompt, ChatPromptTemplate)
    msgs = prompt.format_messages(transcript="hello")
    assert "helper" in str(msgs[0].content)
    assert "hello" in str(msgs[1].content)


def test_intent_and_confirm_yaml_are_chat_prompt_templates() -> None:
    from voice_enable_mcp.prompts_loader import chat_prompt_from_yaml

    intent = chat_prompt_from_yaml("intent.yml")
    confirm = chat_prompt_from_yaml("confirm.yml")
    assert isinstance(intent, ChatPromptTemplate)
    assert isinstance(confirm, ChatPromptTemplate)
    msgs = intent.format_messages(transcript="create contract with AVC CR 1001")
    assert "AVC" in str(msgs[1].content)


def test_intent_chain_is_lcel() -> None:
    payload = VoiceIntentPayload(
        create_contract=True,
        legal_entity_name="AVC",
        contract_reference_number="CR 1001",
        confidence=0.95,
    )
    llm = RunnableLambda(lambda _messages: payload)
    chain = build_intent_chain(llm)
    result = chain.invoke({"transcript": "please create contract with legal entity AVC CR 1001"})
    assert result.create_contract is True
    assert result.legal_entity_name == "AVC"
    confirm_chain = build_confirm_chain(RunnableLambda(lambda _m: {"confirmed": True}))
    out = confirm_chain.invoke({"user_text": "yes", "suggested_ref": "CR-1001"})
    assert out["confirmed"] is True


def test_parse_voice_transcript_regex_fallback_without_llm() -> None:
    parsed = parse_voice_transcript(
        "please create contract with legal entity AVC contract reference number CR 1001"
    )
    assert parsed.create_contract is True
    assert parsed.legal_entity_name == "AVC"
    assert parsed.notes == "regex"


def test_parse_voice_transcript_uses_lcel_when_llm_returns(monkeypatch) -> None:
    from voice_enable_mcp.services import voice_lcel as mod

    class _Cfg:
        provider = "fake"
        model = "fake-model"

    monkeypatch.setattr(
        mod,
        "_mapper_llm",
        lambda _schema: (RunnableLambda(lambda _m: None), _Cfg()),
    )

    def _fake_invoke(chain, payload, **_kwargs):
        assert payload["transcript"]
        return VoiceIntentPayload(
            create_contract=True,
            legal_entity_name="AVC",
            contract_reference_number="CR 1001",
            confidence=0.88,
            notes="lcel",
        )

    monkeypatch.setattr(mod, "traced_invoke", _fake_invoke)
    parsed = parse_voice_transcript("please create a contract for AVC using CR 1001")
    assert parsed.notes == "lcel"
    assert parsed.legal_entity_name == "AVC"
