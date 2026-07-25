from app.schemas import ChatCompletionRequest, ChatMessage

class EnrichmentService:
    @staticmethod
    def enrich_request(request: ChatCompletionRequest, team_config: dict) -> ChatCompletionRequest:
        enrichment_rules = team_config.get("enrichment", {})
        default_system_prompt = enrichment_rules.get("default_system_prompt")
        
        # Check if system prompt already exists in messages
        has_system_prompt = any(msg.role == "system" for msg in request.messages)

        # Inject default team system prompt if none provided
        if not has_system_prompt and default_system_prompt:
            request.messages.insert(0, ChatMessage(role="system", content=default_system_prompt))

        return request

    @staticmethod
    def enrich_response_text(content: str, team_config: dict) -> str:
        enrichment_rules = team_config.get("enrichment", {})
        disclaimer = enrichment_rules.get("compliance_disclaimer", "")

        if disclaimer and not content.endswith(disclaimer):
            return content + disclaimer

        return content

enrichment_service = EnrichmentService()
