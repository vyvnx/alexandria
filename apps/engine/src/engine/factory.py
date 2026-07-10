from alexandria_core.config import Settings
from alexandria_core.logging_config import get_logger
from alexandria_core.providers.base import LLMProvider, EmbeddingProvider, VisionProvider
from alexandria_core.providers.fake import FakeLLM, FakeEmbedder

log = get_logger("llm")


def build_llm(settings: Settings, over_budget=None) -> LLMProvider:
    if settings.llm == "fake":
        log.info("LLM provider: fake (no real extraction)")
        return FakeLLM()
    if settings.llm == "openai":
        if not settings.openai_api_key:
            log.warning("ALEX_LLM=openai but no API key set — calls will fail")
        from .openai_provider import OpenAIProvider

        providers: dict[str, OpenAIProvider] = {}

        def get(url: str) -> OpenAIProvider:
            # one provider per distinct url — tasks sharing a server share it
            if url not in providers:
                providers[url] = OpenAIProvider(
                    api_key=settings.openai_api_key, model=settings.openai_model,
                    base_url=url or None)
            return providers[url]

        overrides = {task: getattr(settings, f"{task}_base_url")
                     for task in ("summarize", "extract", "relate", "same_topic")}
        overrides = {task: url for task, url in overrides.items() if url}
        if not overrides and not settings.fallback_base_url:
            log.info("LLM provider: openai (model=%s, base_url=%s)",
                     settings.openai_model, settings.openai_base_url or "default")
            return get(settings.openai_base_url)

        from .router import RoutedLLM
        log.info("LLM provider: openai routed (model=%s, overrides=%s, fallback=%s)",
                 settings.openai_model, sorted(overrides) or "none",
                 settings.fallback_base_url or "none")
        return RoutedLLM(
            get(settings.openai_base_url),
            {task: get(url) for task, url in overrides.items()},
            fallback=get(settings.fallback_base_url) if settings.fallback_base_url else None,
            over_budget=over_budget)
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
