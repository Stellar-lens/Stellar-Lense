from typing import Protocol, Dict, Any, List, Optional, runtime_checkable
from dataclasses import dataclass, field

@dataclass
class ServiceHealth:
    status: str
    details: Dict[str, Any] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)

@runtime_checkable
class HealthCheckable(Protocol):
    def healthcheck(self) -> ServiceHealth:
        ...

@runtime_checkable
class MetricsProvider(Protocol):
    def get_metrics(self) -> Dict[str, Any]:
        ...

@runtime_checkable
class ConfigurableService(Protocol):
    def configure(self, config: Dict[str, Any]) -> None:
        ...

@runtime_checkable
class SecretSanitizer(Protocol):
    def sanitize(self, text: str) -> str:
        ...

class ServiceRegistry:
    def __init__(self) -> None:
        self._services: Dict[str, Any] = {}

    def register(self, name: str, service: Any) -> None:
        self._services[name] = service

    def get(self, name: str) -> Optional[Any]:
        return self._services.get(name)

    def check_all_health(self) -> Dict[str, ServiceHealth]:
        results: Dict[str, ServiceHealth] = {}
        for name, service in self._services.items():
            if isinstance(service, HealthCheckable):
                results[name] = service.healthcheck()
            else:
                results[name] = ServiceHealth(
                    status="UNKNOWN",
                    details={"error": "Service does not implement HealthCheckable"}
                )
        return results

    def collect_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        metrics: Dict[str, Dict[str, Any]] = {}
        for name, service in self._services.items():
            if isinstance(service, MetricsProvider):
                metrics[name] = service.get_metrics()
        return metrics

default_registry = ServiceRegistry()
