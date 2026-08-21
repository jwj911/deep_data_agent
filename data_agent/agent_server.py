from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from data_agent.config.config import ConfigurationError, config
from data_agent.config.database import init_db
from data_agent.config.logger import agent_logger
from data_agent.models.user import User
from data_agent.observability.context import get_or_create_request_id
from data_agent.observability.middleware import (REQUEST_ID_HEADER,
                                                 ObservabilityMiddleware)
from data_agent.observability.rate_limit_middleware import RateLimitMiddleware
from data_agent.readiness import check_readiness_async
from data_agent.routes import admin, auth, managed_file, session
from data_agent.security.upload_limit_middleware import \
    FileUploadBodyLimitMiddleware
from data_agent.services.agent_lease import (AGENT_BUSY, AgentBusyError,
                                             AgentProtectionUnavailableError)
from data_agent.services.agent_service import (AGENT_MODEL_BUDGET_EXCEEDED,
                                               AGENT_TOOL_BUDGET_EXCEEDED,
                                               AgentInvocationError,
                                               AgentModelBudgetExceededError,
                                               AgentQueryValidationError,
                                               AgentResponseTooLargeError,
                                               AgentTimeoutError,
                                               AgentToolBudgetExceededError,
                                               global_agent_service)
from data_agent.services.authorization_service import (Permission,
                                                       require_permission)
from data_agent.services.redis_recovery import AGENT_PROTECTION_UNAVAILABLE


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Run database initialization when the FastAPI service starts."""
    init_db()
    yield


app = FastAPI(
    title="Deep Data Agent API",
    description="API for interacting with the Deep Data Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.CORS_ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
    expose_headers=[REQUEST_ID_HEADER],
)
app.add_middleware(FileUploadBodyLimitMiddleware)
# 中间件“后 add = 更外层”。此处按 CORS、FileLimit、RateLimit、Observability 添加，
# 使执行顺序为 Observability -> RateLimit -> FileLimit -> CORS -> route。
# Observability 最外层先绑定请求 ID，限流的 429 分支才能取到 request_id。
app.add_middleware(RateLimitMiddleware)
app.add_middleware(ObservabilityMiddleware)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(session.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(
    managed_file.router,
    prefix="/api/files",
    tags=["files"],
)


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        max_length=config.AGENT_QUERY_MAX_CHARS,
    )

    @field_validator("query")
    @classmethod
    def _reject_blank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query cannot be blank")
        return value


class QueryResponse(BaseModel):
    response: str = Field(max_length=config.AGENT_RESPONSE_MAX_CHARS)


def _error_detail(code: str, message: str, request_id: str) -> dict[str, str]:
    return {
        "code": code,
        "message": message,
        "request_id": request_id,
    }


@app.post("/api/query", response_model=QueryResponse)
async def query_agent(
    request: QueryRequest,
    current_user: User = Depends(
        require_permission(Permission.AGENT_INVOKE_OWN)
    ),
):
    """Endpoint for querying the agent"""
    request_id = get_or_create_request_id()
    try:
        response = await global_agent_service.ainvoke(
            request.query,
            actor=current_user,
            request_id=request_id,
        )
        return QueryResponse(response=response)
    except AgentQueryValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_detail(
                "agent_invalid_query",
                "Query must be non-blank and within the size limit",
                request_id,
            ),
        ) from exc
    except AgentBusyError as exc:
        raise HTTPException(
            status_code=429,
            detail=_error_detail(
                AGENT_BUSY,
                "Agent concurrency limit reached",
                request_id,
            ),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except AgentProtectionUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=_error_detail(
                AGENT_PROTECTION_UNAVAILABLE,
                "Agent protection is temporarily unavailable",
                request_id,
            ),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except AgentModelBudgetExceededError as exc:
        raise HTTPException(
            status_code=429,
            detail=_error_detail(
                AGENT_MODEL_BUDGET_EXCEEDED,
                "Agent model-call budget exceeded",
                request_id,
            ),
        ) from exc
    except AgentToolBudgetExceededError as exc:
        raise HTTPException(
            status_code=429,
            detail=_error_detail(
                AGENT_TOOL_BUDGET_EXCEEDED,
                "Agent tool-call budget exceeded",
                request_id,
            ),
        ) from exc
    except AgentTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=_error_detail(
                "agent_timeout",
                "Agent request timed out",
                request_id,
            ),
        ) from exc
    except AgentResponseTooLargeError as exc:
        raise HTTPException(
            status_code=502,
            detail=_error_detail(
                "agent_response_too_large",
                "Agent response exceeded the size limit",
                request_id,
            ),
        ) from exc
    except ConfigurationError as exc:
        agent_logger.warning(
            "Query rejected by configuration request_id=%s", request_id
        )
        raise HTTPException(
            status_code=503,
            detail=_error_detail(
                "agent_not_configured", str(exc), request_id
            ),
        ) from exc
    except AgentInvocationError as exc:
        raise HTTPException(
            status_code=502,
            detail=_error_detail(
                "agent_upstream_error",
                "Agent service is temporarily unavailable",
                request_id,
            ),
        ) from exc
    except Exception as exc:
        agent_logger.exception(
            "Unexpected query failure request_id=%s", request_id
        )
        raise HTTPException(
            status_code=500,
            detail=_error_detail(
                "internal_error",
                "Internal server error",
                request_id,
            ),
        ) from exc


@app.get("/api/live")
@app.get("/api/health")
async def health_check():
    """Report process liveness without checking external dependencies."""
    return {"status": "healthy"}


@app.get("/api/ready")
async def readiness_check():
    """Report shallow dependency readiness without external API calls."""
    request_id = get_or_create_request_id()
    result = await check_readiness_async()
    return JSONResponse(
        status_code=200 if result.ready else 503,
        content=result.response_payload(request_id),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "data_agent.agent_server:app",
        host=config.FASTAPI_HOST,
        port=config.FASTAPI_PORT,
        reload=True,
    )
