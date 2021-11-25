# Copyright (c) 2021, NVIDIA CORPORATION.
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

from .info_coll_cmd import ClientInfoProcessor
from .process_aux_cmd import AuxRequestProcessor
from .shell_cmd import ShellCommandProcessor
from .sys_cmd import SysInfoProcessor
from .training_cmds import (
    AbortAppProcessor,
    ClientStatusProcessor,
    DeleteRunNumberProcessor,
    DeployProcessor,
    RestartClientProcessor,
    ShutdownClientProcessor,
    # StartClientMGpuProcessor,
    StartAppProcessor,
    AbortTaskProcessor,
    SetRunNumberProcessor,
)
from .validation_cmd import ValidateRequestProcessor


class ClientRequestProcessors:
    request_processors = [
        StartAppProcessor(),
        ClientStatusProcessor(),
        AbortAppProcessor(),
        ShutdownClientProcessor(),
        DeployProcessor(),
        ValidateRequestProcessor(),
        ShellCommandProcessor(),
        DeleteRunNumberProcessor(),
        SysInfoProcessor(),
        RestartClientProcessor(),
        # StartClientMGpuProcessor(),
        ClientInfoProcessor(),
        AbortTaskProcessor(),
        SetRunNumberProcessor(),
        AuxRequestProcessor()
    ]

    @staticmethod
    def register_cmd_module(request_processor):
        from .admin import RequestProcessor

        assert isinstance(request_processor, RequestProcessor)

        ClientRequestProcessors.request_processors.append(request_processor)