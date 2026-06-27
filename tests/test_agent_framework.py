import pytest
import asyncio
from unittest.mock import MagicMock
from discography_webapp.services.agent import AgentService, PlanningModule, ExecutionModule, LearningModule

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

    db_path = str(tmp_path / "test.db")
    learner = LearningModule(mock_logger, db_path=db_path)
    planner = PlanningModule(str(tmp_path), learner, mock_logger)
    objectives = planner.prioritize_objectives()

    assert len(objectives) == 2
    # Standard priority: functional=1, docs=2
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
    result = await executor.execute_task({"task": "Test Task", "type": "functional"})
    assert result['success'] is True
    assert mock_protocol.sync_repository.called

    # Test milestone task
    result = await executor.execute_task({"task": "Roadmap: Test", "type": "milestone"})
    assert result['success'] is True
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

    db_path = str(tmp_path / "cycle.db")
    service = AgentService(mock_orch, mock_protocol, mock_logger, db_path=db_path, root_dir=str(tmp_path))

    result = await service.run_cycle()

    assert result['status'] == 'completed'
    assert len(result['tasks_executed']) > 0
    assert mock_protocol.extract_roadmap.called

@pytest.mark.asyncio
async def test_agent_learning_loop(mock_orch, mock_protocol, mock_logger, tmp_path):
    # Ensure protocol methods return a coroutine
    mock_protocol.sync_repository.return_value = asyncio.Future()
    mock_protocol.sync_repository.return_value.set_result(None)
    mock_protocol.extract_roadmap.return_value = asyncio.Future()
    mock_protocol.extract_roadmap.return_value.set_result(None)

    # 1. Setup multiple tasks of different types
    (tmp_path / "TODO.md").write_text("- [Search] Task 1\n- [Documentation] Doc 1\n")

    db_path = str(tmp_path / "learning.db")
    service = AgentService(mock_orch, mock_protocol, mock_logger, db_path=db_path, root_dir=str(tmp_path))

    # 2. Simulate high friction for [Documentation]
    # We manually record experience for 'docs' type
    for _ in range(5):
        service.learner.record_experience("docs", "failed", 10.0)

    # 3. Run cycle
    await service.run_cycle()

    # 4. Verify priority boost in PlanningModule
    # [Documentation] originally priority 2, [Search] originally priority 1.
    # High friction in 'docs' should boost it to priority 1 (2-1=1).
    # Since friction is negative in sorting (x['priority'], -friction),
    # the higher friction task with same priority wins.
    objectives = service.planner.prioritize_objectives()

    # objectives[0] should be the boosted Documentation task
    assert any(obj['type'] == 'docs' and obj['priority'] == 1 for obj in objectives)
    assert objectives[0]['type'] == 'docs'
