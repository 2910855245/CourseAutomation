"""fork-COW 进程池 master（仅 Linux）— 内存最小化核心。

原理：
- 本进程启动时预热导入 worker.py / chaoxing_worker.py 的全部依赖（~120MB）
- 每个任务由本进程 fork() 出子进程（写时复制：基础内存页共享，不重复计费）
- 子进程只产生脏页增量（HTTP 缓冲/lxml 树等，实测 ~35MB），对比
  每次全新 spawn 的 ~100MB，每任务省 ~65MB，且省掉解释器+import 启动时间

fork 安全约束：本进程必须保持单线程（多线程 fork 会死锁）。
因此主循环用阻塞式 socket + 轮询管理子进程，不引入任何线程。
Windows 无 fork：TaskRunner 自动回退到原 spawn 模式。

协议（换行分隔 JSON，127.0.0.1:{port}）：
  {"cmd": "run", "task_id": "...", "script": "worker.py|chaoxing_worker.py",
   "params_file": "...", "status_file": "...", "cwd": "..."}
  -> 立即返回 {"ok": true}
  {"cmd": "cancel", "task_id": "..."} -> {"ok": true/false}
  {"cmd": "stats"} -> {"ok": true, "running": N}

子进程结束前把退出码写入 {status_file同目录}/pool_exit.json，
TaskRunner 轮询该文件得知退出码。
"""
import json
import os
import signal
import socket
import sys
import time

LISTEN_HOST = "127.0.0.1"
POOL_EXIT_SUFFIX = "pool_exit.json"


def _log(msg: str):
    sys.stderr.write(f"[pool-master] {msg}\n")
    sys.stderr.flush()


class ChildInfo:
    __slots__ = ("task_id", "pid", "exit_file", "status_file")

    def __init__(self, task_id, pid, exit_file, status_file):
        self.task_id = task_id
        self.pid = pid
        self.exit_file = exit_file
        self.status_file = status_file


class PoolMaster:
    def __init__(self, port: int):
        self.port = port
        self.children: dict = {}  # task_id -> ChildInfo
        self._srv: socket.socket = None
        self._conn: socket.socket = None  # 当前连接（单连接串行协议足够：请求极小）
        self._buf = b""

    # ── 预热：导入两个 worker 的依赖（fork 后子进程共享这些页）──

    def warmup(self):
        """预导入 worker 依赖，最大化 COW 共享（不实际执行任务）。"""
        _log("预热导入 worker 模块...")
        t0 = time.time()
        try:
            import worker  # noqa: F401  （模块导入即完成全部顶层 import）
            _log(f"worker.py 预热完成 ({time.time() - t0:.1f}s)")
        except Exception as e:
            _log(f"worker.py 预热失败（不影响运行，fork 后子进程自行导入）: {e}")
        t0 = time.time()
        try:
            import chaoxing_worker  # noqa: F401
            _log(f"chaoxing_worker.py 预热完成 ({time.time() - t0:.1f}s)")
        except Exception as e:
            _log(f"chaoxing_worker.py 预热失败: {e}")

    # ── 主循环 ──

    def serve_forever(self):
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((LISTEN_HOST, self.port))
        self._srv.listen(8)
        self._srv.setblocking(False)
        _log(f"监听 {LISTEN_HOST}:{self.port}")

        while True:
            # 收割已退出子进程 + 更新退出文件
            self._reap()
            # 处理一个连接上的所有待处理请求
            try:
                self._poll_conn()
            except Exception as e:
                _log(f"连接异常: {e}")
                self._close_conn()
            time.sleep(0.05)

    def _poll_conn(self):
        if self._conn is None:
            try:
                conn, _ = self._srv.accept()
            except BlockingIOError:
                return
            conn.setblocking(False)
            self._conn = conn
            self._buf = b""
        try:
            data = self._conn.recv(65536)
        except BlockingIOError:
            data = None
        if data == b"" or data is None:
            # 无新数据；处理缓冲内完整行
            pass
        else:
            self._buf += data
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line.decode("utf-8"))
                resp = self._handle(req)
            except Exception as e:
                resp = {"ok": False, "message": f"协议错误: {e}"}
            try:
                self._conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
            except OSError:
                self._close_conn()
                return
        if data == b"":
            self._close_conn()

    def _close_conn(self):
        if self._conn:
            try:
                self._conn.close()
            except OSError:
                pass
        self._conn = None
        self._buf = b""

    # ── 请求处理 ──

    def _handle(self, req: dict) -> dict:
        cmd = req.get("cmd")
        if cmd == "run":
            return self._cmd_run(req)
        if cmd == "cancel":
            return self._cmd_cancel(req)
        if cmd == "stats":
            return {"ok": True, "running": len(self.children)}
        return {"ok": False, "message": f"未知命令: {cmd}"}

    def _cmd_run(self, req: dict) -> dict:
        task_id = req.get("task_id", "")
        script = req.get("script", "")
        params_file = req.get("params_file", "")
        status_file = req.get("status_file", "")
        cwd = req.get("cwd", "") or os.path.dirname(os.path.abspath(__file__))
        if not task_id or not params_file:
            return {"ok": False, "message": "task_id/params_file 必填"}
        if script not in ("worker.py", "chaoxing_worker.py"):
            return {"ok": False, "message": f"未知 script: {script}"}
        if task_id in self.children:
            return {"ok": False, "message": "task_id 已存在"}
        if not hasattr(os, "fork"):
            return {"ok": False, "message": "fork 不可用（仅 Linux 支持）"}

        # fork 前清掉 SIGCHLD 自定义处理（子进程用默认行为）
        exit_file = os.path.join(os.path.dirname(status_file), POOL_EXIT_SUFFIX)
        if os.path.exists(exit_file):
            try:
                os.remove(exit_file)
            except OSError:
                pass

        pid = os.fork()
        if pid == 0:
            # ── 子进程：复刻 worker __main__ 的语义（信号→优雅退出标记、异常→错误状态、终态兜底）──
            code = 1
            try:
                os.chdir(cwd)
                sys.path.insert(0, cwd)
                module_name = script[:-3]  # worker / chaoxing_worker
                mod = __import__(module_name)
                from worker_common import ensure_terminal_status, send_status

                def _handle_signal(signum, frame):
                    # 与 worker.__main__ 一致：置 _shutdown_requested，任务循环自行退出
                    try:
                        mod._shutdown_requested = True
                    except Exception:
                        os._exit(0)

                signal.signal(signal.SIGTERM, _handle_signal)
                signal.signal(signal.SIGINT, _handle_signal)

                code = 0
                try:
                    mod.run_task(params_file, status_file)
                except SystemExit as e:
                    code = e.code if isinstance(e.code, int) else 0
                except BaseException:
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                    code = 1
                    try:
                        send_status(status_file, phase="error", message="任务异常",
                                    done=True, success=False)
                    except Exception:
                        pass
                finally:
                    try:
                        ensure_terminal_status(status_file)
                    except Exception:
                        pass
            except BaseException:
                import traceback
                traceback.print_exc(file=sys.stderr)
            try:
                with open(exit_file, "w", encoding="utf-8") as f:
                    json.dump({"exit_code": code}, f)
            except OSError:
                pass
            os._exit(code)

        self.children[task_id] = ChildInfo(task_id, pid, exit_file, status_file)
        _log(f"fork 子进程 task_id={task_id} pid={pid} script={script}")
        return {"ok": True, "pid": pid}

    def _cmd_cancel(self, req: dict) -> dict:
        task_id = req.get("task_id", "")
        info = self.children.get(task_id)
        if not info:
            return {"ok": False, "message": "任务不存在"}
        try:
            os.kill(info.pid, signal.SIGTERM)
            return {"ok": True}
        except ProcessLookupError:
            return {"ok": True}

    def _reap(self):
        """收割已退出的子进程（非阻塞），保证退出文件存在。"""
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return
            if pid == 0:
                return
            for task_id, info in list(self.children.items()):
                if info.pid == pid:
                    if not os.path.exists(info.exit_file):
                        try:
                            with open(info.exit_file, "w", encoding="utf-8") as f:
                                json.dump({"exit_code": 0}, f)
                        except OSError:
                            pass
                    self.children.pop(task_id, None)
                    _log(f"子进程退出 task_id={task_id} pid={pid}")
                    break


def main():
    port = int(os.environ.get("WORKER_POOL_PORT", "17019"))
    master = PoolMaster(port)
    master.warmup()
    master.serve_forever()


if __name__ == "__main__":
    main()
