# Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
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

import json
from typing import List

import psutil

from nvflare.fuel.hci.conn import Connection
from nvflare.fuel.hci.proto import MetaKey, MetaStatusValue, make_meta
from nvflare.fuel.hci.reg import CommandModule, CommandModuleSpec, CommandSpec
from nvflare.fuel.hci.server.authz import PreAuthzReturnCode
from nvflare.fuel.utils.log_utils import dynamic_log_config
from nvflare.private.admin_defs import MsgHeader, ReturnCode
from nvflare.private.defs import SysCommandTopic
from nvflare.private.fed.server.admin import new_message
from nvflare.private.fed.server.cmd_utils import CommandUtil
from nvflare.private.fed.server.server_engine import ServerEngine
from nvflare.security.logging import secure_format_exception


def _parse_replies(conn, replies):
    """parses resources from replies."""
    site_resources = {}
    for r in replies:
        client_name = r.client_name

        if r.reply:
            if r.reply.get_header(MsgHeader.RETURN_CODE) == ReturnCode.ERROR:
                resources = r.reply.body
            else:
                try:
                    resources = json.loads(r.reply.body)
                except Exception as e:
                    resources = f"Bad replies: {secure_format_exception(e)}"
        else:
            resources = "No replies"
        site_resources[client_name] = resources
    return site_resources


class SystemCommandModule(CommandModule, CommandUtil):
    def get_spec(self):
        return CommandModuleSpec(
            name="sys",
            cmd_specs=[
                CommandSpec(
                    name="sys_info",
                    description="get the system info",
                    usage="sys_info server|client <client-name> ...",
                    handler_func=self.sys_info,
                    authz_func=self.authorize_server_operation,
                    visible=True,
                ),
                CommandSpec(
                    name="configure_site_log",
                    description="configure logging of a site",
                    usage="configure_site_log server|client <client-name>... config",
                    handler_func=self.configure_site_log,
                    authz_func=self.authorize_configure_site_log,
                    visible=True,
                ),
                CommandSpec(
                    name="report_resources",
                    description="get the resources info",
                    usage="report_resources server | client <client-name> ...",
                    handler_func=self.report_resources,
                    authz_func=self.authorize_server_operation,
                    visible=True,
                ),
                CommandSpec(
                    name="report_env",
                    description="get env info of a client",
                    usage="report_env <client-name>",
                    handler_func=self.report_env,
                    authz_func=self.authorize_client_operation,
                    visible=True,
                ),
                CommandSpec(
                    name="dead",
                    description="send dead client msg to SJ",
                    usage="dead <client-name>",
                    handler_func=self.dead_client,
                    authz_func=self.must_be_project_admin,
                    visible=False,
                ),
            ],
        )

    def authorize_configure_site_log(self, conn: Connection, args: List[str]):
        if len(args) < 3:
            conn.append_error("syntax error: please provide target_type and config")
            return PreAuthzReturnCode.ERROR
        return self.authorize_server_operation(conn, args[:-1])

    def sys_info(self, conn: Connection, args: [str]):
        if len(args) < 2:
            conn.append_error("syntax error: missing site names")
            return

        target_type = args[1]
        if target_type == self.TARGET_TYPE_SERVER:
            infos = dict(psutil.virtual_memory()._asdict())

            table = conn.append_table(["Metrics", "Value"])

            for k, v in infos.items():
                table.add_row([str(k), str(v)])
            table.add_row(
                [
                    "available_percent",
                    "%.1f" % (psutil.virtual_memory().available * 100 / psutil.virtual_memory().total),
                ]
            )
            return

        if target_type == self.TARGET_TYPE_CLIENT:
            message = new_message(conn, topic=SysCommandTopic.SYS_INFO, body="", require_authz=True)
            replies = self.send_request_to_clients(conn, message)
            self._process_replies(conn, replies)
            return

        conn.append_string("invalid target type {}. Usage: sys_info server|client <client-name>".format(target_type))

    def configure_site_log(self, conn: Connection, args: [str]):
        if len(args) < 3:
            conn.append_error("syntax error: please provide target_type and config")
            return

        target_type = args[1]
        config = args[-1]

        if target_type in [self.TARGET_TYPE_SERVER, self.TARGET_TYPE_ALL]:
            engine = conn.app_ctx
            if not isinstance(engine, ServerEngine):
                raise TypeError("engine must be ServerEngine but got {}".format(type(engine)))

            workspace = engine.get_workspace()
            try:
                dynamic_log_config(
                    config=config, dir_path=workspace.get_root_dir(), reload_path=workspace.get_log_config_file_path()
                )
            except Exception as e:
                conn.append_error(
                    secure_format_exception(e),
                    meta=make_meta(MetaStatusValue.INTERNAL_ERROR, info=secure_format_exception(e)),
                )
                return
            conn.append_string("successfully configured server site log")

        if target_type in [self.TARGET_TYPE_CLIENT, self.TARGET_TYPE_ALL]:
            message = new_message(conn, topic=SysCommandTopic.CONFIGURE_SITE_LOG, body=config, require_authz=True)
            replies = self.send_request_to_clients(conn, message)
            self.process_replies_to_table(conn, replies)

        if target_type not in [self.TARGET_TYPE_ALL, self.TARGET_TYPE_CLIENT, self.TARGET_TYPE_SERVER]:
            conn.append_error(
                "invalid target type {}. Usage: configure_site_log server|client <client-name>...|all config".format(
                    target_type
                )
            )

    def _process_replies(self, conn, replies):
        if not replies:
            conn.append_error("no responses from clients")
            return

        for r in replies:
            client_name = r.client_name
            conn.append_string("Client: " + client_name)

            table = conn.append_table(["Metrics", "Value"])
            if r.reply:
                if r.reply.get_header(MsgHeader.RETURN_CODE) == ReturnCode.ERROR:
                    table.add_row([r.reply.body, ""])
                else:
                    try:
                        infos = json.loads(r.reply.body)

                        for k, v in infos.items():
                            table.add_row([str(k), str(v)])
                        table.add_row(
                            [
                                "available_percent",
                                "%.1f" % (psutil.virtual_memory().available * 100 / psutil.virtual_memory().total),
                            ]
                        )
                    except Exception:
                        conn.append_string(": Bad replies")
            else:
                conn.append_string(": No replies")

    def report_resources(self, conn: Connection, args: List[str]):
        if len(args) < 2:
            conn.append_error("syntax error: missing site names")
            return

        target_type = args[1]
        if target_type != self.TARGET_TYPE_CLIENT and target_type != self.TARGET_TYPE_SERVER:
            conn.append_string(
                "invalid target type {}. Usage: sys_info server|client <client-name>".format(target_type)
            )
            return

        site_resources = {"server": "unlimited"}

        if target_type == self.TARGET_TYPE_CLIENT:
            message = new_message(conn, topic=SysCommandTopic.REPORT_RESOURCES, body="", require_authz=True)
            replies = self.send_request_to_clients(conn, message)
            if not replies:
                conn.append_error("no responses from clients")
                return
            site_resources = _parse_replies(conn, replies)

        table = conn.append_table(["Sites", "Resources"])
        for k, v in site_resources.items():
            table.add_row([str(k), str(v)])

    def report_env(self, conn: Connection, args: List[str]):
        message = new_message(conn, topic=SysCommandTopic.REPORT_ENV, body="", require_authz=True)
        replies = self.send_request_to_clients(conn, message)
        if not replies:
            conn.append_error("no responses from clients")
            return
        site_resources = _parse_replies(conn, replies)

        table = conn.append_table(["Sites", "Env"], name=MetaKey.CLIENTS)
        for k, v in site_resources.items():
            table.add_row([str(k), str(v)], meta=v)

    def dead_client(self, conn: Connection, args: List[str]):
        if len(args) != 3:
            conn.append_error(f"Usage: {args[0]} client_name job_id")
            return
        client_name = args[1]
        job_id = args[2]
        engine = conn.app_ctx
        engine.notify_dead_job(job_id, client_name, f"AdminCommand: {args[0]}")
        conn.append_string(f"called notify_dead_job for client {client_name=} {job_id=}")
