"""简答+文件上传题求解器（编程项目提交）"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from typing import Dict, Optional

import httpx
from loguru import logger
from openai import OpenAI


class ProjectSolver:
    """自动完成编程项目提交题：下载案例→AI生成→编译→打包→上传→提交"""

    def __init__(self, session: httpx.Client, base_url: str, api_key: str,
                 student_id: str = "", student_name: str = "",
                 model: str = "deepseek-chat"):
        from infrastructure.exam_login import normalize_base_url
        self.session = session
        self.base_url = normalize_base_url(base_url)
        self.api_key = api_key
        self.model = model
        self.student_id = student_id
        self.student_name = student_name
        self.ai_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    def solve(self, work_id: int, course_id: int, node_id: int,
              question_text: str = "") -> Dict:
        """完整流程"""
        tmpdir = tempfile.mkdtemp(prefix="project_")
        try:
            # 1. 下载案例参考
            logger.info("[project] 下载案例参考...")
            ref_code = self._download_reference(course_id, node_id, tmpdir)

            # 2. AI 生成项目
            logger.info("[project] AI 生成项目...")
            project = self._generate_project(question_text, ref_code)
            if not project.get("source_code"):
                return {"success": False, "error": "AI 生成代码为空"}

            # 3. 编译
            logger.info("[project] 编译 C 代码...")
            exe_path = self._compile(project["source_code"], project["project_name"], tmpdir)
            compiled = exe_path is not None

            # 4. 打包
            logger.info("[project] 打包 zip...")
            zip_path = self._package(project, exe_path, tmpdir)

            # 5. 上传到 COS
            logger.info("[project] 上传文件到 COS...")
            file_url = self._upload_to_cos(zip_path)
            if not file_url:
                return {"success": False, "error": "文件上传失败"}

            # 6. 提交
            logger.info("[project] 提交作业...")
            result = self._submit(work_id, node_id, project, file_url)

            return {
                "success": result.get("status") is not False,
                "file_url": file_url,
                "project_name": project["project_name"],
                "compiled": compiled,
                "submit_result": result,
            }
        except Exception as e:
            logger.error(f"[project] 异常: {e}")
            return {"success": False, "error": str(e)}
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _download_reference(self, course_id: int, node_id: int, tmpdir: str) -> str:
        """从课程树找到案例节点，下载并提取源代码"""
        try:
            # 案例节点通常是当前节点的前一个
            case_node_id = int(node_id) - 1 if str(node_id).isdigit() else 0
            if not case_node_id:
                return ""

            # 访问案例节点页面，提取下载链接
            resp = self.session.get(
                f"{self.base_url}/user/node",
                params={"courseId": course_id, "nodeId": case_node_id},
                timeout=15,
            )
            html = resp.text

            # 提取下载链接: <a href="..." download="...">立即下载</a>
            match = re.search(r'href="(https?://[^"]*\.(?:zip|rar))"[^>]*download', html)
            if not match:
                match = re.search(r'href="([^"]*\.(?:zip|rar))"[^>]*download', html)
            if not match:
                logger.warning("[project] 未找到案例下载链接")
                return ""

            download_url = match.group(1)
            if download_url.startswith("/"):
                download_url = self.base_url + download_url

            # 下载 zip
            dl_resp = self.session.get(download_url, timeout=30)
            zip_path = os.path.join(tmpdir, "reference.zip")
            with open(zip_path, "wb") as f:
                f.write(dl_resp.content)

            # 解压并读取 .c 文件
            ref_dir = os.path.join(tmpdir, "reference")
            os.makedirs(ref_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(ref_dir)

            c_files = []
            for root, dirs, files in os.walk(ref_dir):
                for f in files:
                    if f.endswith((".c", ".h")):
                        filepath = os.path.join(root, f)
                        try:
                            with open(filepath, encoding="utf-8") as fh:
                                c_files.append(f"// {f}\n{fh.read()}")
                        except Exception:
                            try:
                                with open(filepath, encoding="gbk") as fh:
                                    c_files.append(f"// {f}\n{fh.read()}")
                            except Exception:
                                pass

            code = "\n\n".join(c_files)
            logger.info(f"[project] 案例代码 {len(c_files)} 个文件, {len(code)} 字符")
            return code[:8000]  # 限制长度避免 token 超限
        except Exception as e:
            logger.warning(f"[project] 下载案例失败: {e}")
            return ""

    def _generate_project(self, question_text: str, ref_code: str) -> Dict:
        """用 AI 生成 C 语言项目"""
        ref_section = ""
        if ref_code:
            ref_section = f"""

以下是案例项目的源代码，供参考（不要完全复制，需要有自己的功能和风格）：
```c
{ref_code}
```"""

        prompt = f"""你是一个 C 语言编程专家。请根据以下作业要求，生成一个完整的 C 语言项目。

作业要求：
{question_text}
{ref_section}

要求：
1. 生成一个完整的 .c 源代码文件（可直接用 gcc 编译运行）
2. 功能完整、界面友好（使用控制台菜单交互）
3. 包含基本的增删改查功能
4. 代码规范，有适当注释
5. 使用中文界面

请返回严格的 JSON 格式（不要包含其他文本）：
{{
  "project_name": "项目名称（中文）",
  "source_code": "完整的 C 语言源代码",
  "description": "项目功能简述（50字以内）"
}}"""

        try:
            resp = self.ai_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4096,
            )
            content = resp.choices[0].message.content.strip()

            # 提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(content)

            return {
                "project_name": data.get("project_name", "C语言项目"),
                "source_code": data.get("source_code", ""),
                "description": data.get("description", ""),
            }
        except Exception as e:
            logger.error(f"[project] AI 生成失败: {e}")
            return {"project_name": "C语言项目", "source_code": "", "description": ""}

    def _compile(self, source_code: str, project_name: str, tmpdir: str) -> Optional[str]:
        """编译 C 代码，返回可执行文件路径"""
        c_file = os.path.join(tmpdir, "main.c")
        exe_file = os.path.join(tmpdir, "main.exe")

        with open(c_file, "w", encoding="utf-8") as f:
            f.write(source_code)

        try:
            result = subprocess.run(
                ["gcc", "-o", exe_file, c_file, "-lm"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and os.path.exists(exe_file):
                logger.info("[project] 编译成功")
                return exe_file
            else:
                logger.warning(f"[project] 编译失败: {result.stderr[:300]}")
                return None
        except FileNotFoundError:
            logger.warning("[project] gcc 未安装，跳过编译")
            return None
        except subprocess.TimeoutExpired:
            logger.warning("[project] 编译超时")
            return None

    def _package(self, project: Dict, exe_path: Optional[str], tmpdir: str) -> str:
        """按要求目录结构打包 zip"""
        project_name = project.get("project_name", "C语言项目")
        sid = self.student_id or "student"
        sname = self.student_name or "name"
        dir_name = f"{sid}{sname}"

        # 创建目录结构
        pkg_dir = os.path.join(tmpdir, "package", dir_name, project_name)
        os.makedirs(pkg_dir, exist_ok=True)

        # 写源代码
        c_path = os.path.join(pkg_dir, "main.c")
        with open(c_path, "w", encoding="utf-8") as f:
            f.write(project["source_code"])

        # 写使用说明书
        readme = os.path.join(pkg_dir, "使用说明书.txt")
        with open(readme, "w", encoding="utf-8") as f:
            f.write(f"项目名称：{project_name}\n")
            f.write(f"功能说明：{project.get('description', '')}\n\n")
            f.write("使用方法：\n")
            f.write("1. 编译：gcc -o main main.c -lm\n")
            f.write("2. 运行：./main（Linux）或 main.exe（Windows）\n")
            f.write("3. 按照菜单提示操作\n")

        # 复制可执行文件
        if exe_path and os.path.exists(exe_path):
            shutil.copy2(exe_path, os.path.join(pkg_dir, "main.exe"))

        # 打包 zip
        zip_path = os.path.join(tmpdir, f"{dir_name}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(os.path.join(tmpdir, "package")):
                for f in files:
                    filepath = os.path.join(root, f)
                    arcname = os.path.relpath(filepath, os.path.join(tmpdir, "package"))
                    zf.write(filepath, arcname)

        logger.info(f"[project] 打包完成: {zip_path} ({os.path.getsize(zip_path)} bytes)")
        return zip_path

    def _upload_to_cos(self, zip_path: str) -> Optional[str]:
        """上传文件到腾讯云 COS，返回文件 URL"""
        try:
            # 1. 获取签名
            sign_resp = self.session.get(
                f"{self.base_url}/service/txcos/sign",
                params={"method": "post", "pathname": "/"},
                timeout=10,
            )
            sign_data = sign_resp.json()
            if sign_data.get("error"):
                logger.error(f"[project] COS 签名失败: {sign_data['error']}")
                return None

            cos_url = sign_data["_url"]
            web_url = sign_data["_web_url"].rstrip("/")
            auth = sign_data["Authorization"]
            token = sign_data.get("XCosSecurityToken", "")

            # 2. 生成随机 key
            import random
            chars = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"
            rand_str = "".join(random.choices(chars, k=20))
            key = f"upfiles/{rand_str}.zip"

            # 3. 上传到 COS
            with open(zip_path, "rb") as f:
                file_data = f.read()

            form_data = {
                "key": key,
                "Signature": auth,
                "Content-Type": "",
            }
            if token:
                form_data["x-cos-security-token"] = token

            files = {"file": (os.path.basename(zip_path), file_data, "application/zip")}
            upload_resp = httpx.post(cos_url, data=form_data, files=files, timeout=60)

            if upload_resp.status_code // 100 == 2:
                file_url = f"{web_url}/{key}"
                logger.info(f"[project] 上传成功: {file_url}")
                return file_url
            else:
                logger.error(f"[project] 上传失败: HTTP {upload_resp.status_code}")
                return None
        except Exception as e:
            logger.error(f"[project] 上传异常: {e}")
            return None

    def _submit(self, work_id: int, node_id: int, project: Dict, file_url: str) -> Dict:
        """提交作业表单"""
        try:
            # 先访问 work 页面获取 answerId
            resp = self.session.get(
                f"{self.base_url}/user/work",
                params={"workId": work_id, "nodeId": node_id},
                timeout=15,
            )
            html = resp.text

            # 提取 answerId
            answer_id_match = re.search(r'name="answerId"[^>]*value="(\d+)"', html)
            answer_id = answer_id_match.group(1) if answer_id_match else ""

            if not answer_id:
                logger.error("[project] 未找到 answerId")
                return {"status": False, "msg": "未找到 answerId"}

            # 构造文件引用
            file_name = f"{self.student_id}{self.student_name}.zip"
            files_json = json.dumps([{"url": file_url, "name": file_name}])

            # 提交
            submit_data = {
                "workId": str(work_id),
                "answerId": answer_id,
                "answer": f"项目名称：{project['project_name']}\n{project.get('description', '')}",
                "images": "[]",
                "files": files_json,
            }

            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": f"{self.base_url}/user/work?workId={work_id}&nodeId={node_id}",
            }

            submit_resp = self.session.post(
                f"{self.base_url}/user/work/submit",
                data=submit_data,
                headers=headers,
                timeout=15,
            )

            result = submit_resp.json()
            logger.info(f"[project] 提交结果: {result}")
            return result
        except Exception as e:
            logger.error(f"[project] 提交异常: {e}")
            return {"status": False, "msg": str(e)}
