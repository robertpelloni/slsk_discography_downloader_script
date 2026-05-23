from fastapi import APIRouter, BackgroundTasks, Request, Depends
from services.protocol import ProtocolService
from dependencies import get_orchestrator

router = APIRouter()

def get_protocol_service(request: Request):
    orch = get_orchestrator(request.app.state.event_bus)
    return ProtocolService(orch.logger)

@router.post("/api/maintenance/sync")
async def sync_repo(background_tasks: BackgroundTasks, protocol: ProtocolService = Depends(get_protocol_service)):
    background_tasks.add_task(protocol.sync_repository)
    return {"message": "Repository sync started in background"}

@router.post("/api/maintenance/reconcile")
async def reconcile_branches(background_tasks: BackgroundTasks, protocol: ProtocolService = Depends(get_protocol_service)):
    background_tasks.add_task(protocol.reconcile_branches)
    return {"message": "Branch reconciliation started in background"}

@router.post("/api/maintenance/roadmap")
async def extract_roadmap(background_tasks: BackgroundTasks, protocol: ProtocolService = Depends(get_protocol_service)):
    background_tasks.add_task(protocol.extract_roadmap)
    return {"message": "Roadmap extraction started in background"}

@router.post("/api/maintenance/full_protocol")
async def full_protocol(background_tasks: BackgroundTasks, protocol: ProtocolService = Depends(get_protocol_service)):
    async def run_full():
        await protocol.sync_repository()
        await protocol.reconcile_branches()
        await protocol.extract_roadmap()

    background_tasks.add_task(run_full)
    return {"message": "Full Autonomous Protocol execution started in background"}
