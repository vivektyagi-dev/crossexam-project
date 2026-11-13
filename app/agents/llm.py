"""Model factory. Switch providers with one setting (LLM_PROVIDER)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import settings

# Tests (and offline demos) can register a factory that returns a scripted model.
_fake_factory: Callable[[str], BaseChatModel] | None = None


def register_fake_factory(factory: Callable[[str], BaseChatModel] | None) -> None:
    global _fake_factory
    _fake_factory = factory


def get_chat_model(tier_or_name: str = "mid", **kwargs: Any) -> BaseChatModel:
    """tier_or_name: 'small' | 'mid' | 'strong' | 'fallback' | 'vision' | an explicit model id."""
    name = {
        "small": settings.model_small,
        "mid": settings.model_mid,
        "strong": settings.model_strong,
        "fallback": settings.model_fallback,
        "vision": settings.model_vision,
    }.get(tier_or_name, tier_or_name)

    provider = settings.llm_provider
    if settings.llm_temperature is not None:
        kwargs.setdefault("temperature", settings.llm_temperature)
    if provider == "fake":
        if _fake_factory is None:
            _load_fake_factory_from_env()
        return _fake_factory(name)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=name,
            google_api_key=settings.google_api_key or None,
            max_retries=0,  # retries are handled by ModelRetryMiddleware so they are visible
            **kwargs,
        )
    if provider == "vertex":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=name,
            vertexai=True,
            project=settings.gcp_project or None,
            location=settings.gcp_location,
            max_retries=0,
            **kwargs,
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=name, api_key=settings.openai_api_key or None, max_retries=0, **kwargs)
    raise ValueError(f"Unknown LLM_PROVIDER {provider}")


def _load_fake_factory_from_env() -> None:
    """FAKE_LLM_FACTORY=module:function lets worker processes use the scripted test model."""
    import importlib
    import os

    spec = os.environ.get("FAKE_LLM_FACTORY")
    if not spec:
        raise RuntimeError("LLM_PROVIDER=fake needs FAKE_LLM_FACTORY=module:function (tests and CI only).")
    module, func = spec.split(":")
    register_fake_factory(getattr(importlib.import_module(module), func))


def model_name(model: BaseChatModel) -> str:
    for attr in ("model", "model_name"):
        value = getattr(model, attr, None)
        if isinstance(value, str):
            return value.replace("models/", "")
    return type(model).__name__


def embed_text(text: str) -> list[float] | None:
    """Embedding for similar-case search. Returns None when embeddings are unavailable,
    in which case the similar_cases tool falls back to supplier + issue-code matching."""
    if settings.llm_provider == "fake" or not settings.enable_pgvector:
        return None
    try:
        if settings.llm_provider in ("gemini", "vertex"):
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            emb = GoogleGenerativeAIEmbeddings(
                model=settings.embedding_model,
                google_api_key=settings.google_api_key or None,
            )
            vec = emb.embed_query(text, output_dimensionality=settings.embedding_dim)
        else:
            from langchain_openai import OpenAIEmbeddings

            vec = OpenAIEmbeddings(model="text-embedding-3-small", dimensions=settings.embedding_dim,
                                   api_key=settings.openai_api_key or None).embed_query(text)
        return list(vec)[: settings.embedding_dim]
    except Exception:  # embeddings are an enhancement, never a blocker
        return None
