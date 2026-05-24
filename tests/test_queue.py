"""Tests for task queue: submit/claim/cancel/retry jobs, WAITING status, stats."""
import time
from unittest.mock import patch, MagicMock

import pytest

from api.services.task_queue import (
    QueueJob,
    QueueJobStatus,
    QueueManager,
    _model_to_job,
    get_combined_stats,
    get_queue_by_job_id,
    get_queue_for_type,
)

# Alias for brevity
def _submit(q, **kwargs):
    """Helper to call submit_job with defaults."""
    defaults = dict(username="user1", password="pass", website_id=1)
    defaults.update(kwargs)
    return q.submit_job(**defaults)


class TestQueueJob:
    def test_default_values(self):
        job = QueueJob()
        assert job.status == "pending"
        assert job.progress == 0.0
        assert job.retry_count == 0
        assert job.max_retries == 3

    def test_to_dict(self):
        job = QueueJob(job_id="J-001", username="test", website_id=1)
        d = job.to_dict()
        assert d["job_id"] == "J-001"
        assert d["username"] == "test"
        assert "password" not in d  # password should not be in dict

    def test_priority_ordering(self):
        j1 = QueueJob(priority=1)
        j2 = QueueJob(priority=2)
        assert j1 < j2


class TestModelToJob:
    def test_conversion(self):
        mock_model = MagicMock()
        mock_model.job_id = "J-001"
        mock_model.username = "user1"
        mock_model.password = "pass"
        mock_model.website_id = 1
        mock_model.job_type = "video"
        mock_model.course_ids = '[1, 2]'
        mock_model.status = "pending"
        mock_model.priority = 0
        mock_model.progress = 50.0
        mock_model.total_steps = 10
        mock_model.completed_steps = 5
        mock_model.current_step_name = "step5"
        mock_model.error_message = ""
        mock_model.retry_count = 0
        mock_model.max_retries = 3
        mock_model.task_id = None
        mock_model.order_id = "O-001"
        mock_model.result_data = '{"key": "value"}'
        mock_model.verified = False
        mock_model.created_at = "2026-01-01T00:00:00"
        mock_model.started_at = None
        mock_model.finished_at = None

        job = _model_to_job(mock_model)
        assert job.job_id == "J-001"
        assert job.course_ids == [1, 2]
        assert job.result_data == {"key": "value"}


class TestQueueRouting:
    def test_chaoxing_points_goes_to_chaoxing(self):
        q = get_queue_for_type("chaoxing_points")
        assert q._name == "chaoxing"

    def test_video_goes_to_school(self):
        q = get_queue_for_type("video")
        assert q._name == "school"

    def test_exam_goes_to_school(self):
        q = get_queue_for_type("exam")
        assert q._name == "school"


class TestQueueManagerOperations:
    @pytest.fixture
    def queue(self, tmp_path):
        """Create a QueueManager with an in-memory SQLite database."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from api.db.models import Base, SchoolJobModel

        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(bind=engine)
        TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        q = QueueManager(SchoolJobModel, TestSession, name="test")
        return q

    def test_submit_job(self, queue):
        job = _submit(queue, job_type="video")
        assert job.job_id
        assert job.status == "pending"
        assert job.username == "user1"

    def test_get_job(self, queue):
        job = _submit(queue)
        retrieved = queue.get_job(job.job_id)
        assert retrieved is not None
        assert retrieved.job_id == job.job_id

    def test_claim_job(self, queue):
        job = _submit(queue)
        result = queue._db_claim_job(job.job_id)
        assert result is True
        updated = queue.get_job(job.job_id)
        assert updated.status == "running"

    def test_claim_already_running_fails(self, queue):
        job = _submit(queue)
        queue._db_claim_job(job.job_id)
        result = queue._db_claim_job(job.job_id)
        assert result is False

    def test_cancel_job(self, queue):
        job = _submit(queue)
        result = queue.cancel_job(job.job_id)
        assert result is True
        updated = queue.get_job(job.job_id)
        assert updated.status == "cancelled"

    def test_cancel_running_job(self, queue):
        job = _submit(queue)
        queue._db_claim_job(job.job_id)
        result = queue.cancel_job(job.job_id)
        assert result is True

    def test_retry_failed_job(self, queue):
        job = _submit(queue)
        queue._db_update(job.job_id, status=QueueJobStatus.FAILED, error_message="test error")
        result = queue.retry_job(job.job_id)
        assert result is True
        updated = queue.get_job(job.job_id)
        assert updated.status == "pending"
        assert updated.retry_count == 0

    def test_retry_non_failed_job_fails(self, queue):
        job = _submit(queue)
        result = queue.retry_job(job.job_id)
        assert result is False

    def test_list_jobs(self, queue):
        _submit(queue, username="u1", password="p1")
        _submit(queue, username="u2", password="p2")
        jobs = queue.list_jobs()
        assert len(jobs) >= 2

    def test_list_jobs_filtered(self, queue):
        job = _submit(queue, username="u1", password="p1")
        _submit(queue, username="u2", password="p2")
        queue._db_update(job.job_id, status=QueueJobStatus.FAILED)
        failed = queue.list_jobs(status="failed")
        assert all(j.status == "failed" for j in failed)

    def test_get_stats(self, queue):
        _submit(queue, username="u1", password="p1")
        _submit(queue, username="u2", password="p2")
        stats = queue.get_stats()
        assert stats["total"] >= 2
        assert stats["pending"] >= 2
        assert "running" in stats
        assert "waiting" in stats

    def test_duplicate_job_prevention(self, queue):
        _submit(queue, username="user1", order_id="O-001")
        _submit(queue, username="user1", order_id="O-001")
        jobs = queue.list_jobs()
        order_jobs = [j for j in jobs if j.order_id == "O-001"]
        assert len(order_jobs) == 1


class TestWaitingStatus:
    @pytest.fixture
    def queue(self, tmp_path):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from api.db.models import Base, SchoolJobModel

        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(bind=engine)
        TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        return QueueManager(SchoolJobModel, TestSession, name="test")

    def test_waiting_job_not_picked_by_dispatcher(self, queue):
        job = _submit(queue)
        queue._db_update(job.job_id, status=QueueJobStatus.WAITING)
        pending = queue._db_pending_jobs()
        pending_ids = [j.job_id for j in pending]
        assert job.job_id not in pending_ids

    def test_check_waiting_jobs_resumes_yesterday(self, queue):
        job = _submit(queue)
        yesterday = "2026-05-22T18:00:00"
        queue._db_update(
            job.job_id,
            status=QueueJobStatus.WAITING,
            finished_at=yesterday,
        )
        from datetime import datetime as real_dt
        fake_now = real_dt(2026, 5, 23, 14, 0, 0)
        with patch("api.services.task_queue.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.strptime = real_dt.strptime
            queue._check_waiting_jobs()
        updated = queue.get_job(job.job_id)
        assert updated.status == "pending"

    def test_check_waiting_jobs_keeps_today(self, queue):
        job = _submit(queue)
        today = "2026-05-23T18:00:00"
        queue._db_update(
            job.job_id,
            status=QueueJobStatus.WAITING,
            finished_at=today,
        )
        from datetime import datetime as real_dt
        fake_now = real_dt(2026, 5, 23, 14, 0, 0)
        with patch("api.services.task_queue.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.strptime = real_dt.strptime
            queue._check_waiting_jobs()
        updated = queue.get_job(job.job_id)
        assert updated.status == "waiting"

    def test_check_waiting_jobs_timeout_30_days(self, queue):
        job = _submit(queue)
        old_date = "2026-04-20T18:00:00"
        queue._db_update(
            job.job_id,
            status=QueueJobStatus.WAITING,
            finished_at=old_date,
            created_at="2026-04-15T00:00:00",
        )
        from datetime import datetime as real_dt
        fake_now = real_dt(2026, 5, 23, 14, 0, 0)
        with patch("api.services.task_queue.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.strptime = real_dt.strptime
            queue._check_waiting_jobs()
        updated = queue.get_job(job.job_id)
        assert updated.status == "failed"
        assert "30天" in updated.error_message


class TestJobByOrderId:
    @pytest.fixture
    def queue(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from api.db.models import Base, SchoolJobModel

        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(bind=engine)
        TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        return QueueManager(SchoolJobModel, TestSession, name="test")

    def test_get_job_by_order_id(self, queue):
        _submit(queue, username="u1", password="p1", order_id="O-001")
        job = queue.get_job_by_order_id("O-001")
        assert job is not None
        assert job.order_id == "O-001"

    def test_get_nonexistent_order(self, queue):
        job = queue.get_job_by_order_id("O-NONE")
        assert job is None


class TestCombinedStats:
    def test_get_combined_stats_keys(self):
        stats = get_combined_stats()
        assert "pending" in stats
        assert "running" in stats
        assert "waiting" in stats
        assert "completed" in stats
        assert "failed" in stats
