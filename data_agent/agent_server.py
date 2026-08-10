from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from data_agent.config.config import ConfigurationError, config
from data_agent.config.database import init_db
from data_agent.config.logger import agent_logger
from data_agent.observability.context import get_or_create_request_id
from data_agent.observability.middleware import (REQUEST_ID_HEADER,
                                                 ObservabilityMiddleware)
from data_agent.observability.rate_limit_middleware import RateLimitMiddleware
from data_agent.routes import auth, session
from data_agent.services.agent_service import (AgentInvocationError,
                                               global_agent_service)


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
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
    expose_headers=[REQUEST_ID_HEADER],
)
# 中间件“后 add = 更外层”。此处按 CORS、RateLimit、Observability 顺序添加，
# 使执行顺序为 Observability(最外) -> RateLimit -> CORS(最内，最靠近路由)。
# Observability 最外层先绑定请求 ID，限流的 429 分支才能取到 request_id。
app.add_middleware(RateLimitMiddleware)
app.add_middleware(ObservabilityMiddleware)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(session.router, prefix="/api/sessions", tags=["sessions"])


class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    response: str


def _error_detail(code: str, message: str, request_id: str) -> dict[str, str]:
    return {
        "code": code,
        "message": message,
        "request_id": request_id,
    }


@app.post("/api/query", response_model=QueryResponse)
async def query_agent(request: QueryRequest):
    """Endpoint for querying the agent"""
    request_id = get_or_create_request_id()
    try:
        response = global_agent_service.invoke(
            request.query, request_id=request_id
        )
        return QueryResponse(response=response)
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


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "data_agent.agent_server:app",
        host=config.FASTAPI_HOST,
        port=config.FASTAPI_PORT,
        reload=True,
    )
