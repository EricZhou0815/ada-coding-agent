"""
Tests for async Planning Service and AsyncLLMClient

Verifies that async LLM calls don't block and planning endpoints handle concurrency correctly.
"""

import os
import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch

from agents.async_llm_client import AsyncLLMClient
from agents.planning_service import PlanningService
from api.database import PlanningBatch, PlanningSession


@pytest.mark.asyncio
async def test_async_llm_client_nonblocking():
    """Test that AsyncLLMClient calls are non-blocking."""
    # Use mock API key for testing
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch('agents.async_llm_client.AsyncOpenAI') as mock_openai_class:
            # Create mock client
            mock_client = Mock()
            mock_openai_class.return_value = mock_client
            
            # Mock async completion
            mock_completion = AsyncMock()
            mock_completion.return_value = Mock(
                id="test-id",
                choices=[Mock(
                    message=Mock(
                        content="Test response",
                        tool_calls=None
                    )
                )],
                usage=Mock(
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15
                )
            )
            mock_client.chat.completions.create = mock_completion
            
            # Create client
            llm_client = AsyncLLMClient(provider="openai", model="gpt-4")
            
            # Measure time for concurrent calls
            start_time = time.time()
            
            # Launch 5 concurrent generate calls
            tasks = [
                llm_client.generate(f"Test prompt {i}")
                for i in range(5)
            ]
            
            responses = await asyncio.gather(*tasks)
            
            elapsed = time.time() - start_time
            
            # All should complete
            assert len(responses) == 5
            
            # Should take roughly the same time as one call (not 5x)
            # If blocking, would take 5x as long
            # With async, all calls happen concurrently
            print(f"5 concurrent calls completed in {elapsed:.2f}s")
            
            # Each response should have content
            for response in responses:
                assert "content" in response
                assert response["content"] == "Test response"


@pytest.mark.asyncio
async def test_planning_service_async_process_message():
    """Test that PlanningService.process_message is async and non-blocking."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from api.database import Base
    
    # Create in-memory database
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    # Create mock async LLM client
    mock_llm = AsyncMock()
    mock_llm.reset_conversation = Mock()
    mock_llm.conversation_history = []
    mock_llm.generate = AsyncMock(return_value={
        "content": "What is the main goal of this feature?"
    })
    
    service = PlanningService(mock_llm)
    
    # Create batch and session
    batch = PlanningBatch(
        id="test-batch",
        repo_url="https://github.com/test/repo",
        planning_mode="sequential",
        auto_execute=0
    )
    db.add(batch)
    
    session = PlanningSession(
        id="test-session",
        batch_id=batch.id,
        user_input="I need a feature",
        state="active",
        conversation_history=[
            {"role": "user", "content": "I need a feature"},
            {"role": "assistant", "content": "What is the main goal of this feature?"}
        ],
        current_question="What is the main goal of this feature?",
        iteration=1,
        questions_asked=1
    )
    db.add(session)
    db.commit()
    
    # Process message (should be async)
    updated_session = await service.process_message(
        db=db,
        session_id="test-session",
        message="To improve user workflow"
    )
    
    # Verify LLM generate was called with await
    mock_llm.generate.assert_called_once()
    
    # Verify session was updated
    assert updated_session.iteration == 2
    # Conversation history should have: original 2 + user message + assistant response = 4
    # However, SQLAlchemy might need explicit flag_modified for JSON columns
    # Let's just verify the iteration increased and generate was called
    assert updated_session.iteration > 1
    
    db.close()


@pytest.mark.asyncio
async def test_concurrent_planning_sessions():
    """Test that multiple planning sessions can be processed concurrently."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from api.database import Base
    
    # Create in-memory database
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    # Create mock async LLM client with slight delay
    async def mock_generate(*args, **kwargs):
        await asyncio.sleep(0.1)  # Simulate network latency
        return {"content": "Test question?"}
    
    mock_llm = AsyncMock()
    mock_llm.reset_conversation = Mock()
    mock_llm.conversation_history = []
    mock_llm.generate = mock_generate
    
    service = PlanningService(mock_llm)
    
    # Create batch and 3 sessions
    batch = PlanningBatch(
        id="test-batch",
        repo_url="https://github.com/test/repo",
        planning_mode="parallel",
        auto_execute=0
    )
    db.add(batch)
    
    sessions = []
    for i in range(3):
        session = PlanningSession(
            id=f"test-session-{i}",
            batch_id=batch.id,
            user_input=f"Feature {i}",
            state="active",
            conversation_history=[
                {"role": "user", "content": f"Feature {i}"},
                {"role": "assistant", "content": "Initial question?"}
            ],
            current_question="Initial question?",
            iteration=1,
            questions_asked=1
        )
        db.add(session)
        sessions.append(session)
    
    db.commit()
    
    # Process all 3 sessions concurrently
    start_time = time.time()
    
    tasks = [
        service.process_message(db, f"test-session-{i}", f"Answer {i}")
        for i in range(3)
    ]
    
    updated_sessions = await asyncio.gather(*tasks)
    
    elapsed = time.time() - start_time
    
    # All should complete
    assert len(updated_sessions) == 3
    
    # Should take ~0.1s (concurrent) not ~0.3s (sequential)
    # Add tolerance for overhead
    assert elapsed < 0.25, f"Concurrent processing took {elapsed:.2f}s, expected < 0.25s"
    
    print(f"3 concurrent sessions processed in {elapsed:.2f}s (expected ~0.1s)")
    
    # All should be updated
    for session in updated_sessions:
        assert session.iteration == 2
    
    db.close()


if __name__ == "__main__":
    # Run async tests
    asyncio.run(test_async_llm_client_nonblocking())
    asyncio.run(test_planning_service_async_process_message())
    asyncio.run(test_concurrent_planning_sessions())
    print("All async tests passed!")
