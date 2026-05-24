"""Tests for api/services/error_classifier.py — 错误分类器"""


class TestClassify:
    """错误分类逻辑测试"""

    def test_fatal_password_error(self):
        from api.services.error_classifier import ErrorClassifier

        assert ErrorClassifier.classify("密码错误") == "fatal"

    def test_fatal_account_disabled(self):
        from api.services.error_classifier import ErrorClassifier

        assert ErrorClassifier.classify("账号被禁用") == "fatal"

    def test_fatal_account_not_exist(self):
        from api.services.error_classifier import ErrorClassifier

        assert ErrorClassifier.classify("账号不存在") == "fatal"

    def test_fatal_student_not_found(self):
        from api.services.error_classifier import ErrorClassifier

        assert ErrorClassifier.classify("学生信息不存在") == "fatal"

    def test_fatal_exam_not_supported(self):
        from api.services.error_classifier import ErrorClassifier

        assert ErrorClassifier.classify("暂不支持期末考试") == "fatal"

    def test_fatal_zero_progress(self):
        from api.services.error_classifier import ErrorClassifier

        assert ErrorClassifier.classify("平台实际进度仅0%") == "fatal"

    def test_retryable_study_timeout(self):
        from api.services.error_classifier import ErrorClassifier

        assert ErrorClassifier.classify("刷课超时") == "retryable"

    def test_retryable_login_failed(self):
        from api.services.error_classifier import ErrorClassifier

        assert ErrorClassifier.classify("登录平台失败") == "retryable"

    def test_retryable_video_download_failed(self):
        from api.services.error_classifier import ErrorClassifier

        assert ErrorClassifier.classify("视频下载失败") == "retryable"

    def test_retryable_process_interrupted(self):
        from api.services.error_classifier import ErrorClassifier

        assert ErrorClassifier.classify("刷课进程已中断") == "retryable"

    def test_unknown_defaults_to_retryable(self):
        from api.services.error_classifier import ErrorClassifier

        assert ErrorClassifier.classify("一些未知错误信息") == "retryable"

    def test_empty_message(self):
        from api.services.error_classifier import ErrorClassifier

        assert ErrorClassifier.classify("") == "retryable"

    def test_none_message(self):
        from api.services.error_classifier import ErrorClassifier

        assert ErrorClassifier.classify(None) == "retryable"

    def test_marked_prefix_stripped(self):
        from api.services.error_classifier import ErrorClassifier

        assert ErrorClassifier.classify("[已标记]密码错误") == "fatal"

    def test_marked_prefix_retryable(self):
        from api.services.error_classifier import ErrorClassifier

        assert ErrorClassifier.classify("[已标记]刷课超时") == "retryable"

    def test_deleted_by_teacher_is_fatal(self):
        from api.services.error_classifier import ErrorClassifier
        assert ErrorClassifier.classify("已被老师删除") == "fatal"

    def test_password_empty_is_retryable(self):
        from api.services.error_classifier import ErrorClassifier
        assert ErrorClassifier.classify("密码不能为空") == "retryable"

    def test_status_file_lost_is_retryable(self):
        from api.services.error_classifier import ErrorClassifier
        assert ErrorClassifier.classify("状态文件丢失") == "retryable"


class TestPatternIntegrity:
    """Verify pattern lists are consistent."""

    def test_no_overlap(self):
        from api.services.error_classifier import ErrorClassifier
        overlap = set(ErrorClassifier.RETRYABLE_PATTERNS) & set(ErrorClassifier.FATAL_PATTERNS)
        assert len(overlap) == 0, f"Overlapping patterns: {overlap}"

    def test_retryable_not_empty(self):
        from api.services.error_classifier import ErrorClassifier
        assert len(ErrorClassifier.RETRYABLE_PATTERNS) > 0

    def test_fatal_not_empty(self):
        from api.services.error_classifier import ErrorClassifier
        assert len(ErrorClassifier.FATAL_PATTERNS) > 0
