# Abstractions

Contract layer for the Rivex backend template. Every concrete type in sibling packages must implement the matching interface here.

## Layout

```
abstractions/
├── configuration.py   # IConfiguration — singleton, validated, loadable
├── controller.py      # IController — Rivex Controller + request context
├── dependency.py      # IDependency — Rivex Depends() targets
├── error.py           # IError / DomainError hierarchy
├── factory.py         # IFactory — wiring and creation
├── model.py           # IModel — persisted entities
├── repository.py      # IRepository — async data access ports
├── service.py         # IService — use-case orchestration
├── utility.py         # IUtility — stateless helpers
├── context.py         # ContextMixin — urn / user tracing
├── singleton.py       # SingletonMeta — thread-safe config singletons
└── logger.py          # ILogger — logger Protocol
```

## Inheritance chain

| Layer            | Package           | Implements        |
|------------------|-------------------|-------------------|
| Configurations   | `configurations/` | `IConfiguration`  |
| Controllers      | `controllers/`    | `IController`     |
| DTOs             | `dtos/`           | `IDto`, `IRequestDto`, `IResponseDto` |
| Models           | `models/`         | `IModel`          |
| Repositories     | `repositories/`   | `IRepository`     |
| Services         | `services/`       | `IService`        |
| Utilities        | `utilities/`      | `IUtility`        |
| Dependencies     | `dependencies/`   | `IDependency`     |
| Factories        | `factories/`      | `IFactory`        |

## Configuration singleton

```python
from abstractions import IConfiguration

class AppConfiguration(IConfiguration):
    @classmethod
    def source(cls) -> str:
        return "env"

    @classmethod
    def layer_name(cls) -> str:
        return "app"

    @classmethod
    def load(cls) -> "AppConfiguration":
        cfg = cls._from_env()
        cfg.validate()
        return cfg

    def validate(self) -> None:
        ...
```

Access anywhere:

```python
config = AppConfiguration.get_instance()
```

## Controller example

```python
from rivex import get
from abstractions import IController

class ItemsController(IController):
    path = "/items"
    tags = ["items"]

    @classmethod
    def base_path(cls) -> str:
        return cls.path

    @get("/")
    async def list_items(self):
        ...
```

## Logging (logx)

Structured logging uses the in-house logx SDK. Initialize at startup:

```python
from utilities.logger_adapter import init_logging, get_logger

init_logging(level="info", log_file="logs/app.ndjson")

logger = get_logger(component="items_service")
logger.info("item_created", item_id="...")
```

Request-scoped loggers are bound automatically via `ContextMixin`:

```python
self.logger.info("request_completed", status=200)
```
