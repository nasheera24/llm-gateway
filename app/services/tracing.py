import time
from typing import Dict, Any, Optional
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

# Initialize OpenTelemetry SDK
provider = TracerProvider()
# Add Console Exporter for inspectable spans
processor = SimpleSpanProcessor(ConsoleSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("llm-gateway", "1.0.0")

class TracingService:
    def __init__(self):
        self.tracer = tracer

    def start_span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        span = self.tracer.start_span(name)
        if attributes:
            for k, v in attributes.items():
                if v is not None:
                    span.set_attribute(k, str(v) if isinstance(v, (dict, list)) else v)
        return span

tracing_service = TracingService()
