from alexandria_core.config import Settings
from alexandria_core.logging_config import get_logger
from alexandria_core.providers.base import LLMProvider, EmbeddingProvider, VisionProvider
from alexandria_core.providers.fake import FakeLLM, FakeEmbedder

log = get_logger("llm")


def build_llm(settings: Settings) -> LLMProvider:
    if settings.llm == "fake":
        log.info("LLM provider: fake (no real extraction)")
        return FakeLLM()
    if settings.llm == "openai":
        if not settings.openai_api_key:
            log.warning("ALEX_LLM=openai but no API key set — calls will fail")
        log.info("LLM provider: openai (model=%s, base_url=%s)",
                 settings.openai_model, settings.openai_base_url or "default")
        from .openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=settings.openai_api_key, model=settings.openai_model,
                              base_url=settings.openai_base_url or None)
    raise ValueError(f"unknown llm provider: {settings.llm}")


def build_embedder(settings: Settings, *, fake: bool = False) -> EmbeddingProvider:
    if fake or settings.llm == "fake":
        log.info("embedder: fake (dim=%d)", settings.embed_dim)
        return FakeEmbedder(dim=settings.embed_dim)
    log.info("embedder: Qwen3 %s (dim=%d) — model loads on first use",
             settings.embed_model, settings.embed_dim)
    from .qwen_embedder import Qwen3Embedder
    return Qwen3Embedder(model_name=settings.embed_model, dim=settings.embed_dim)


def build_vision(settings: Settings) -> VisionProvider:
    if settings.llm == "fake":
        from alexandria_core.providers.fake import FakeVision
        log.info("vision provider: fake")
        return FakeVision()
    if settings.llm == "openai":
        if not settings.openai_api_key:
            log.warning("ALEX_LLM=openai but no API key set — vision calls will fail")
        log.info("vision provider: openai (model=%s)", settings.openai_vision_model)
        from .openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=settings.openai_api_key,
                              model=settings.openai_vision_model,
                              base_url=settings.openai_base_url or None)
    raise ValueError(f"unknown llm provider: {settings.llm}")
