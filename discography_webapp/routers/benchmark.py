from fastapi import APIRouter, Request
from services.benchmark import SearchBenchmark
from dependencies import get_orchestrator
from services.rust_soulseek import RustSoulseekService

router = APIRouter()

def get_bench(request: Request):
    orch = get_orchestrator(request.app.state.event_bus)
    # We might need to ensure rust service is initialized if not already
    if not hasattr(orch, 'rust_slsk') or orch.rust_slsk is None:
        user = orch.config_service.get('slsk_user')
        password = orch.config_service.get('slsk_pass')
        orch.rust_slsk = RustSoulseekService(user, password)

    return SearchBenchmark(orch.slsk_service, orch.rust_slsk)

@router.get("/api/benchmark")
async def run_benchmark(request: Request, query: str = "Infected Mushroom"):
    orch = get_orchestrator(request.app.state.event_bus)

    # 1. Ensure services are initialized
    if not hasattr(orch, 'rust_slsk') or orch.rust_slsk is None:
        user = orch.config_service.get('slsk_user')
        password = orch.config_service.get('slsk_pass')
        orch.rust_slsk = RustSoulseekService(user, password)

    # 2. Connect if not connected (using configured credentials)
    if not orch.slsk_service.is_connected:
        user = orch.config_service.get('slsk_user')
        password = orch.config_service.get('slsk_pass')
        if user and password:
            try:
                await orch.slsk_service.connect(user, password)
                if orch.rust_slsk:
                    await orch.rust_slsk.connect()
            except Exception:
                pass

    bench = SearchBenchmark(orch.slsk_service, orch.rust_slsk)
    results = await bench.run_benchmark(query)
    return results
