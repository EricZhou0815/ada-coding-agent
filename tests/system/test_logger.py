"""
Tests for logging infrastructure and handlers.
"""
import pytest
import json
import os
from unittest.mock import Mock, MagicMock, patch
from utils.logger import (
    LogHandler,
    TerminalHandler,
    DatabaseHandler,
    RedisHandler,
    AdaLogger
)


class TestLogHandler:
    """Test base LogHandler class."""
    
    def test_log_handler_is_abstract(self):
        """LogHandler.emit should raise NotImplementedError."""
        handler = LogHandler()
        
        with pytest.raises(NotImplementedError):
            handler.emit("info", "Test", "message")


class TestTerminalHandler:
    """Test terminal/console output handler."""
    
    def test_terminal_handler_creation(self):
        """Should create terminal handler successfully."""
        handler = TerminalHandler()
        assert handler is not None
    
    @patch('builtins.print')
    def test_emit_info_message(self, mock_print):
        """Should print info messages with color."""
        handler = TerminalHandler()
        handler.emit("info", "Agent", "Processing file.py")
        
        mock_print.assert_called_once()
        call_args = str(mock_print.call_args)
        assert "Agent" in call_args
        assert "Processing file.py" in call_args
    
    @patch('builtins.print')
    def test_emit_error_message(self, mock_print):
        """Should print error messages with red color."""
        handler = TerminalHandler()
        handler.emit("error", "System", "Critical failure")
        
        mock_print.assert_called_once()
        call_args = str(mock_print.call_args)
        assert "System" in call_args
        assert "Critical failure" in call_args
    
    @patch('builtins.print')
    def test_emit_success_message(self, mock_print):
        """Should print success messages with green checkmark."""
        handler = TerminalHandler()
        handler.emit("success", "Agent", "Task completed")
        
        assert mock_print.call_count >= 1
        call_args = str(mock_print.call_args)
        assert "Task completed" in call_args
    
    @patch('builtins.print')
    def test_emit_thought_message(self, mock_print):
        """Should print thoughts with box formatting."""
        handler = TerminalHandler()
        handler.emit("thought", "CodingAgent", "I should check the imports")
        
        # Should print at least two lines
        assert mock_print.call_count >= 2
   
    @patch('builtins.print')
    def test_emit_tool_call(self, mock_print):
        """Should print tool calls with metadata."""
        handler = TerminalHandler()
        metadata = {"args": "file='test.py'"}
        handler.emit("tool", "Agent", "read_file", metadata=metadata)
        
        mock_print.assert_called_once()
        call_args = str(mock_print.call_args)
        assert "read_file" in call_args
        assert "test.py" in call_args
    
    @patch('builtins.print')
    def test_emit_tool_result(self, mock_print):
        """Should print tool results with success indicator."""
        handler = TerminalHandler()
        
        # Success case
        handler.emit("tool_result", "Agent", "", metadata={"success": True, "output_len": 1024})
        assert "✓" in str(mock_print.call_args) or "success" in str(mock_print.call_args).lower()
        
        # Failure case
        handler.emit("tool_result", "Agent", "", metadata={"success": False, "output_len": 0})
        assert "✗" in str(mock_print.call_args) or "fail" in str(mock_print.call_args).lower()
    
    @patch('builtins.print')
    def test_emit_warning_message(self, mock_print):
        """Should print warnings with warning icon."""
        handler = TerminalHandler()
        handler.emit("warning", "System", "Rate limit approaching")
        
        mock_print.assert_called_once()
        call_args = str(mock_print.call_args)
        assert "warning" in call_args.lower() or "⚠" in call_args


class TestDatabaseHandler:
    """Test database log persistence handler."""
    
    def test_database_handler_creation(self):
        """Should create database handler with job ID."""
        handler = DatabaseHandler("job-123")
        assert handler.job_id == "job-123"
    
    @patch('api.database.SessionLocal')
    def test_emit_saves_to_database(self, mock_session_class):
        """Should save structured logs to database using JobLog table."""
        # Setup mocks
        mock_db = MagicMock()
        mock_session_class.return_value = mock_db
        
        # Execute
        handler = DatabaseHandler("job-456")
        handler.emit("info", "Agent", "Test message", metadata={"key": "value"})
        
        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()
        
        # Check that a JobLog object was added
        added_log = mock_db.add.call_args[0][0]
        assert added_log.job_id == "job-456"
        assert added_log.level == "info"
        assert added_log.prefix == "Agent"
        assert added_log.message == "Test message"
        assert added_log.meta == {"key": "value"}
        assert added_log.timestamp is not None
    
    @patch('api.database.SessionLocal')
    def test_emit_creates_multiple_log_entries(self, mock_session_class):
        """Should create multiple independent log entries."""
        mock_db = MagicMock()
        mock_session_class.return_value = mock_db
        
        handler = DatabaseHandler("job-789")
        handler.emit("info", "Worker", "First log entry")
        handler.emit("success", "Worker", "Second log entry")
        
        # Verify two separate inserts happened
        assert mock_db.add.call_count == 2
        assert mock_db.commit.call_count == 2
        
        # Check both log entries
        first_log = mock_db.add.call_args_list[0][0][0]
        second_log = mock_db.add.call_args_list[1][0][0]
        
        assert first_log.message == "First log entry"
        assert second_log.message == "Second log entry"
    
    @patch('api.database.SessionLocal')
    def test_emit_handles_database_error(self, mock_session_class):
        """Should handle database errors gracefully."""
        mock_db = MagicMock()
        mock_session_class.return_value = mock_db
        
        # Simulate database error on commit
        mock_db.commit.side_effect = Exception("Database error")
        
        handler = DatabaseHandler("error-job")
        
        # Should not raise error - handles gracefully
        handler.emit("error", "System", "Test error handling")
        
        # Verify rollback was called
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()


class TestRedisHandler:
    """Test Redis pub/sub log streaming handler."""
    
    @patch('redis.from_url')
    def test_redis_handler_creation(self, mock_redis):
        """Should create Redis handler and connect."""
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        
        handler = RedisHandler("job-redis-123")
        
        assert handler.job_id == "job-redis-123"
        assert handler.r == mock_client
        mock_redis.assert_called_once()
    
    @patch('redis.from_url')
    def test_emit_publishes_to_redis(self, mock_redis):
        """Should publish structured log events to Redis."""
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        
        handler = RedisHandler("job-stream-456")
        handler.emit("info", "Worker", "Processing task", metadata={"task_id": "T1"})
        
        # Verify publish was called
        mock_client.publish.assert_called_once()
        
        # Check channel and message
        call_args = mock_client.publish.call_args
        channel = call_args[0][0]
        message = call_args[0][1]
        
        assert channel == "logs:job-stream-456"
        
        # Parse message
        log_event = json.loads(message)
        assert log_event["level"] == "info"
        assert log_event["prefix"] == "Worker"
        assert log_event["message"] == "Processing task"
        assert log_event["metadata"] == {"task_id": "T1"}
        assert "timestamp" in log_event
    
    @patch('redis.from_url')
    def test_emit_handles_redis_error(self, mock_redis):
        """Should handle Redis connection errors gracefully."""
        mock_client = MagicMock()
        mock_client.publish.side_effect = Exception("Redis connection lost")
        mock_redis.return_value = mock_client
        
        handler = RedisHandler("job-error")
        
        # Should not raise exception
        handler.emit("error", "System", "Redis is down")
        
        # Verify publish was attempted
        mock_client.publish.assert_called_once()
    
    @patch('redis.from_url')
    def test_uses_redis_url_from_env(self, mock_redis):
        """Should use REDIS_URL from environment."""
        with patch.dict(os.environ, {"REDIS_URL": "redis://custom:6380/2"}):
            handler = RedisHandler("job-env")
            
            mock_redis.assert_called_with("redis://custom:6380/2")


class TestAdaLogger:
    """Test the main AdaLogger class."""
    
    def test_logger_initialization(self):
        """Should create logger with default terminal handler."""
        logger = AdaLogger()
        
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], TerminalHandler)
    
    @patch('redis.from_url')
    @patch('api.database.SessionLocal')
    def test_set_job_id_adds_handlers(self, mock_session_class, mock_redis):
        """Should add DB and Redis handlers when job ID is set."""
        logger = AdaLogger()
        initial_handler_count = len(logger.handlers)
        
        logger.set_job_id("job-multi-123")
        
        assert logger.job_id == "job-multi-123"
        # Should have terminal + redis + database handlers
        assert len(logger.handlers) == initial_handler_count + 2
        assert any(isinstance(h, RedisHandler) for h in logger.handlers)
        assert any(isinstance(h, DatabaseHandler) for h in logger.handlers)
    
    @patch('redis.from_url')
    @patch('api.database.SessionLocal')
    def test_set_job_id_idempotent(self, mock_session_class, mock_redis):
        """Should replace old handlers when called multiple times."""
        logger = AdaLogger()
        
        logger.set_job_id("job-123")
        first_handlers = len(logger.handlers)
        
        logger.set_job_id("job-123")  # Call again
        
        # Should still have same number of handlers (old ones replaced)
        assert len(logger.handlers) == first_handlers
    
    @patch.object(TerminalHandler, 'emit')
    def test_info_logs_to_all_handlers(self, mock_emit):
        """Should call emit on all registered handlers."""
        logger = AdaLogger()
        logger.info("Test", "Info message")
        
        mock_emit.assert_called_once_with("info", "Test", "Info message", {})
    
    @patch.object(TerminalHandler, 'emit')
    def test_error_logs_to_all_handlers(self, mock_emit):
        """Should log errors to all handlers."""
        logger = AdaLogger()
        logger.error("System", "Error occurred")
        
        mock_emit.assert_called_once_with("error", "System", "Error occurred", {})
    
    @patch.object(TerminalHandler, 'emit')
    def test_success_logs_to_all_handlers(self, mock_emit):
        """Should log success messages."""
        logger = AdaLogger()
        logger.success("Task completed successfully")
        
        mock_emit.assert_called_once_with("success", "System", "Task completed successfully", {})
    
    @patch.object(TerminalHandler, 'emit')
    def test_thought_logs_to_all_handlers(self, mock_emit):
        """Should log agent thoughts."""
        logger = AdaLogger()
        logger.thought("Agent", "I should refactor this function")
        
        mock_emit.assert_called_once_with("thought", "Agent", "I should refactor this function", {})
    
    @patch.object(TerminalHandler, 'emit')
    def test_tool_call_logs_to_all_handlers(self, mock_emit):
        """Should log tool calls with metadata."""
        logger = AdaLogger()
        logger.tool("Agent", "write_file", {"file": "test.py"})
        
        # Check that emit was called with expected structure
        assert mock_emit.called
        args = mock_emit.call_args[0]
        
        assert args[0] == "tool"
        assert args[1] == "Agent"
        assert args[2] == "write_file"
        metadata = args[3]
        assert metadata["tool_name"] == "write_file"
        assert metadata["args"] == {"file": "test.py"}
        assert "args_display" in metadata
    
    @patch.object(TerminalHandler, 'emit')
    def test_tool_result_logs_success(self, mock_emit):
        """Should log successful tool results."""
        logger = AdaLogger()
        result_msg = "File written successfully"
        logger.tool_result("Agent", True, result_msg, len(result_msg))
        
        # Check that emit was called with expected structure
        assert mock_emit.called
        args = mock_emit.call_args[0]  # Positional arguments
        
        assert args[0] == "tool_result"  # level
        assert args[1] == "Agent"  # prefix
        assert args[2] == "SUCCESS"  # message (formerly empty string, now "SUCCESS")
        metadata = args[3]
        assert metadata["success"] is True
        assert metadata["output_len"] == len(result_msg)
        assert metadata["result"] == result_msg
        assert "result_display" in metadata
        
        metadata = args[3]  # metadata dict
        assert metadata["success"] is True
        assert metadata["output_len"] == len(result_msg)
    
    @patch.object(TerminalHandler, 'emit')
    def test_tool_result_logs_failure(self, mock_emit):
        """Should log failed tool results."""
        logger = AdaLogger()
        result_msg = "File not found"
        logger.tool_result("Agent", False, result_msg, len(result_msg))
        
        # Check that emit was called with expected structure
        assert mock_emit.called
        args = mock_emit.call_args[0]  # Positional arguments
        
        assert args[0] == "tool_result"  # level
        assert args[1] == "Agent"  # prefix
        assert args[2] == "FAILED"  # message
        
        metadata = args[3]  # metadata dict
        assert metadata["success"] is False
        assert metadata["output_len"] == len(result_msg)
    
    @patch.object(TerminalHandler, 'emit')
    def test_warning_logs_to_all_handlers(self, mock_emit):
        """Should log warnings."""
        logger = AdaLogger()
        logger.warning("System", "Rate limit approaching")
        
        mock_emit.assert_called_once_with("warning", "System", "Rate limit approaching", {})
        # Replace terminal handler with mock and add additional mocks
        mock_handler1 = Mock(spec=LogHandler)
        mock_handler2 = Mock(spec=LogHandler)
        mock_handler3 = Mock(spec=LogHandler)
        logger.handlers = [mock_handler1, mock_handler2, mock_handler3]
        
        logger.info("Test", "Message to all")
        
        # All handlers should receive the log
        mock_handler1.emit.assert_called_once()
        mock_handler2.emit.assert_called_once()
        mock_handler3.emit.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
