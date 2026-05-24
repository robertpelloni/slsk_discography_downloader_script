import pytest
import asyncio
import os
from unittest.mock import MagicMock, patch
from discography_webapp.services.agent import AgentService, PlanningModule, ExecutionModule

@pytest.fixture
def mock_logger():
    return MagicMock()

@pytest.fixture
def mock_orch():
    return MagicMock()

@pytest.fixture
def mock_protocol():
    return MagicMock()

def test_planning_module(tmp_path, mock_logger):
    # Create dummy TODO.md
    todo = tmp_path / "TODO.md"
    todo.write_text("- [Search] Fix concurrency\n- [Documentation] Update manual\n")

    planner = PlanningModule(str(tmp_path), mock_logger)
    objectives = planner.prioritize_objectives()

    assert len(objectives) == 2
    assert objectives[0]['type'] == 'functional'
    assert objectives[1]['type'] == 'docs'

@pytest.mark.asyncio
async def test_execution_module(mock_orch, mock_protocol, mock_logger):
    # Ensure protocol methods return a coroutine
    mock_protocol.sync_repository.return_value = asyncio.Future()
    mock_protocol.sync_repository.return_value.set_result(None)
    mock_protocol.extract_roadmap.return_value = asyncio.Future()
    mock_protocol.extract_roadmap.return_value.set_result(None)

    executor = ExecutionModule(mock_orch, mock_protocol, mock_logger)

    # Test functional task
    success = await executor.execute_task({"task": "Test Task", "type": "functional"})
    assert success is True
    assert mock_protocol.sync_repository.called

    # Test milestone task
    success = await executor.execute_task({"task": "Roadmap: Test", "type": "milestone"})
    assert success is True
    assert mock_protocol.extract_roadmap.called

@pytest.mark.asyncio
async def test_agent_service_cycle(mock_orch, mock_protocol, mock_logger, tmp_path):
    # Ensure protocol methods return a coroutine
    mock_protocol.sync_repository.return_value = asyncio.Future()
    mock_protocol.sync_repository.return_value.set_result(None)
    mock_protocol.extract_roadmap.return_value = asyncio.Future()
    mock_protocol.extract_roadmap.return_value.set_result(None)

    # Setup files
    (tmp_path / "TODO.md").write_text("- [Search] Task\n")
    (tmp_path / "ROADMAP.md").write_text("- [ ] Phase X\n")

    service = AgentService(mock_orch, mock_protocol, mock_logger)
    service.root_dir = str(tmp_path)

    result = await service.run_cycle()

    assert result['status'] == 'completed'
    assert len(result['tasks_executed']) > 0
    assert mock_protocol.extract_roadmap.called
