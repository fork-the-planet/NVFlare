# Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import threading
import time

import psutil

from nvflare.apis.fl_constant import FLContextKey, WorkspaceConstants
from nvflare.apis.fl_context import FLContext
from nvflare.apis.fl_exception import UnsafeComponentError
from nvflare.fuel.sec.security_content_service import SecurityContentService
from nvflare.private.fed.runner import Runner
from nvflare.private.fed.server.admin import FedAdminServer
from nvflare.private.fed.server.fed_server import FederatedServer


def monitor_parent_process(runner: Runner, parent_pid, stop_event: threading.Event):
    while True:
        if stop_event.is_set() or not psutil.pid_exists(parent_pid):
            runner.stop()
            break
        time.sleep(1)


def check_parent_alive(parent_pid, stop_event: threading.Event):
    while True:
        if stop_event.is_set() or not psutil.pid_exists(parent_pid):
            pid = os.getpid()
            kill_child_processes(pid)
            os.killpg(os.getpgid(pid), 9)
            break
        time.sleep(1)


def kill_child_processes(parent_pid):
    try:
        parent = psutil.Process(parent_pid)
    except psutil.NoSuchProcess:
        return
    children = parent.children(recursive=True)
    for process in children:
        process.kill()


def create_admin_server(fl_server: FederatedServer, server_conf=None, args=None):
    """To create the admin server.

    Args:
        fl_server: fl_server
        server_conf: server config
        args: command args

    Returns:
        A FedAdminServer.
    """
    admin_server = FedAdminServer(
        cell=fl_server.cell,
        fed_admin_interface=fl_server.engine,
        cmd_modules=fl_server.cmd_modules,
        file_upload_dir=os.path.join(args.workspace, server_conf.get("admin_storage", "tmp")),
        file_download_dir=os.path.join(args.workspace, server_conf.get("admin_storage", "tmp")),
        download_job_url=server_conf.get("download_job_url", "http://"),
    )
    return admin_server


def version_check():
    if sys.version_info >= (3, 13):
        raise RuntimeError(
            "Python versions 3.13 and above are not yet supported. Please use Python version between 3.8 and 3.12."
        )
    if sys.version_info < (3, 8):
        raise RuntimeError(
            "Python versions 3.7 and below are not supported. Please use Python version between 3.8 and 3.12."
        )


def init_security_content_service(workspace_dir):
    content_folder_path = os.path.join(workspace_dir, WorkspaceConstants.STARTUP_FOLDER_NAME)
    os.makedirs(content_folder_path, exist_ok=True)
    SecurityContentService.initialize(content_folder=content_folder_path)


def component_security_check(fl_ctx: FLContext):
    exceptions = fl_ctx.get_prop(FLContextKey.EXCEPTIONS)
    if exceptions:
        for _, exception in exceptions.items():
            if isinstance(exception, UnsafeComponentError):
                print(f"Unsafe component configured, could not start {fl_ctx.get_identity_name()}!!")
                raise RuntimeError(exception)
