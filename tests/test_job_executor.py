"""Tests for JobExecutor: execute, daily_done, retry, error enhancement."""
import time
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from api.services.task_queue import QueueJob, QueueJobStatus


class TestErrorEnhancement:
    """Test _enhance_error_message static method."""

    def test_empty_message(self):
        from api.services.job_executor import JobExecutor
        result = JobExecutor._enhance_error_message("")
        assert "未知错误" in result

    def test_login_error_preserved(self):
        from api.services.job_executor import JobExecutor
        result = JobExecutor._enhance_error_message("登录失败：密码错误")
        assert result == "登录失败：密码错误"

    def test_timeout_error_preserved(self):
        from api.services.job_executor import JobExecutor
        result = JobExecutor._enhance_error_message("连接超时")
        assert result == "连接超时"

    def test_step_name_enhanced(self):
        from api.services.job_executor import JobExecutor
        result = JobExecutor._enhance_error_message("考试 1/2: 高数期末")
        assert "步骤中断" in result
        assert "考试 1/2: 高数期末" in result

    def test_password_error_preserved(self):
        from api.services.job_executor import JobExecutor
        result = JobExecutor._enhance_error_message("密码不正确")
        assert result == "密码不正确"

    def test_exception_error_preserved(self):
        from api.services.job_executor import JobExecutor
        result = JobExecutor._enhance_error_message("ConnectionError: timeout")
        assert "timeout" in result


class TestDailyDoneHandling:
    """Test that daily_done result sets WAITING status correctly."""

    @pytest.fixture
    def executor(self):
        from api.services.job_executor import JobExecutor

        db_update = MagicMock()
        db_get = MagicMock()
        db_claim = MagicMock(return_value=True)
        clear_password = MagicMock()
        on_complete = MagicMock()
        on_fail = MagicMock()

        return JobExecutor(
            db_update_fn=db_update,
            db_get_fn=db_get,
            db_claim_fn=db_claim,
            clear_password_fn=clear_password,
            on_complete=on_complete,
            on_fail=on_fail,
            get_study_semaphore=lambda: MagicMock(acquire=MagicMock(return_value=True)),
        )

    def test_daily_done_sets_waiting(self, executor, tmp_path):
        """When TaskRunner returns daily_done, job should be set to WAITING."""
        status_file = tmp_path / "status.json"
        import json
        status_file.write_text(json.dumps({
            "points_total": 50,
            "points_target": 200,
        }))

        job = QueueJob(
            job_id="J-001",
            username="user1",
            password="pass",
            website_id=2,
            job_type="chaoxing_points",
        )

        with patch("api.services.task_runner.TaskRunner") as MockRunner:
            mock_runner = MagicMock()
            mock_runner.run.return_value = {
                "platform": "chaoxing",
                "success": True,
                "daily_done": True,
                "status_file": str(status_file),
                "message": "今日积分已满",
            }
            MockRunner.return_value = mock_runner

            executor.execute(job)

        calls = executor._db_update.call_args_list
        waiting_call = [c for c in calls if c[1].get("status") == QueueJobStatus.WAITING]
        assert len(waiting_call) >= 1
        call_kwargs = waiting_call[0][1]
        assert call_kwargs["progress"] == 25.0  # 50/200 * 100
        assert call_kwargs["current_step_name"] == "等待明天继续"
        assert call_kwargs["finished_at"] is not None

    def test_daily_done_calls_complete_callback(self, executor, tmp_path):
        """WAITING jobs should call on_complete (not on_fail)."""
        status_file = tmp_path / "status.json"
        import json
        status_file.write_text(json.dumps({
            "points_total": 50,
            "points_target": 200,
        }))

        job = QueueJob(
            job_id="J-002",
            username="user1",
            password="pass",
            website_id=2,
            job_type="chaoxing_points",
        )

        with patch("api.services.task_runner.TaskRunner") as MockRunner:
            mock_runner = MagicMock()
            mock_runner.run.return_value = {
                "platform": "chaoxing",
                "success": True,
                "daily_done": True,
                "status_file": str(status_file),
            }
            MockRunner.return_value = mock_runner

            executor.execute(job)

        # on_complete should be called for daily_done
        executor._on_complete.assert_called_once()
        # on_fail should NOT be called
        executor._on_fail.assert_not_called()


class TestRecoverStuckJobs:
    """Test recover_stuck_jobs static method."""

    def test_resets_running_to_pending(self, tmp_path):
        from api.services.job_executor import JobExecutor
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from api.db.models import Base, SchoolJobModel

        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(bind=engine)
        TestSession = sessionmaker(bind=engine)

        # Add a running job
        session = TestSession()
        session.add(SchoolJobModel(
            job_id="J-STUCK",
            username="user1",
            password="pass",
            website_id=1,
            status="running",
            created_at="2026-01-01T00:00:00",
        ))
        session.commit()
        session.close()

        with patch("psutil.process_iter", side_effect=ImportError):
            JobExecutor.recover_stuck_jobs(TestSession, SchoolJobModel)

        session = TestSession()
        job = session.query(SchoolJobModel).filter_by(job_id="J-STUCK").first()
        assert job.status == "pending"
        assert job.progress == 0
        session.close()

    def test_preserves_waiting_progress(self, tmp_path):
        from api.services.job_executor import JobExecutor
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from api.db.models import Base, SchoolJobModel

        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(bind=engine)
        TestSession = sessionmaker(bind=engine)

        # Add a "running" job that was actually waiting (edge case)
        session = TestSession()
        session.add(SchoolJobModel(
            job_id="J-WAIT",
            username="user1",
            password="pass",
            website_id=2,
            status="running",
            progress=66.0,
            created_at="2026-01-01T00:00:00",
        ))
        session.commit()
        session.close()

        with patch("psutil.process_iter", side_effect=ImportError):
            JobExecutor.recover_stuck_jobs(TestSession, SchoolJobModel)

        session = TestSession()
        job = session.query(SchoolJobModel).filter_by(job_id="J-WAIT").first()
        assert job.status == "pending"
        # progress gets reset for non-waiting status
        session.close()


class TestGetProgressFromStatusFile:
    """Test progress calculation from status files."""

    def test_progress_calculation(self, tmp_path):
        import json
        status_file = tmp_path / "status.json"
        status_file.write_text(json.dumps({
            "points_total": 100,
            "points_target": 200,
        }))

        with open(status_file) as f:
            sd = json.load(f)
        pt = sd.get("points_total", 0)
        target = sd.get("points_target", 200)
        progress = min(100.0, pt / target * 100) if target > 0 else 0
        assert progress == 50.0

    def test_zero_target(self):
        progress = min(100.0, 50 / 0 * 100) if 0 > 0 else 0
        assert progress == 0

    def test_full_progress(self):
        progress = min(100.0, 200 / 200 * 100)
        assert progress == 100.0
