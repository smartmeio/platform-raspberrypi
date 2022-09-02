# Copyright 2014-present PlatformIO <contact@platformio.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import platform

from platformio.public import PlatformBase


class RaspberrypiPlatform(PlatformBase):

    def is_embedded(self):
        return True

    def configure_default_packages(self, variables, targets):
        # configure arduino core package.
        # select the right one based on the build.core, disable other one.
        board = variables.get("board")
        board_config = self.board_config(board)
        build_core = variables.get(
            "board_build.core", board_config.get("build.core", "arduino"))

        frameworks = variables.get("pioframework", [])
        if "arduino" in frameworks:
            if build_core == "arduino":
                self.frameworks["arduino"]["package"] = "framework-arduino-mbed"
                self.packages["framework-arduinopico"]["optional"] = True
                self.packages["toolchain-rp2040-earlephilhower"]["optional"] = True 
                self.packages.pop("toolchain-rp2040-earlephilhower", None)
            elif build_core == "earlephilhower":
                self.frameworks["arduino"]["package"] = "framework-arduinopico"
                self.packages["framework-arduino-mbed"]["optional"] = True
                self.packages.pop("toolchain-gccarmnoneeabi", None)
                self.packages["toolchain-rp2040-earlephilhower"]["optional"] = False                
            elif build_core == "arancino":
                self.frameworks["arduino"]["package"] = "framework-arduino-rp2040-arancino"
                self.packages["framework-arduino-mbed"]["optional"] = True
                self.packages.pop("toolchain-gccarmnoneeabi", None)
                self.packages["toolchain-rp2040-earlephilhower"]["optional"] = False
            else:
                sys.stderr.write(
                    "Error! Unknown build.core value '%s'. Don't know which Arduino core package to use." % build_core)
                env.Exit(1)

        # if we want to build a filesystem, we need the tools.
        if "buildfs" in targets:
            self.packages["tool-mklittlefs-rp2040-earlephilhower"]["optional"] = False

        # configure J-LINK tool
        jlink_conds = [
            "jlink" in variables.get(option, "")
            for option in ("upload_protocol", "debug_tool")
        ]
        if variables.get("board"):
            board_config = self.board_config(variables.get("board"))
            jlink_conds.extend([
                "jlink" in board_config.get(key, "")
                for key in ("debug.default_tools", "upload.protocol")
            ])
        jlink_pkgname = "tool-jlink"
        if not any(jlink_conds) and jlink_pkgname in self.packages:
            del self.packages[jlink_pkgname]

        return super().configure_default_packages(variables, targets)

    def get_boards(self, id_=None):
        result = super().get_boards(id_)
        if not result:
            return result
        if id_:
            return self._add_default_debug_tools(result)
        else:
            for key in result:
                result[key] = self._add_default_debug_tools(result[key])
        return result

    def _add_default_debug_tools(self, board):
        debug = board.manifest.get("debug", {})
        upload_protocols = board.manifest.get("upload", {}).get(
            "protocols", [])
        if "tools" not in debug:
            debug["tools"] = {}

        for link in ("cmsis-dap", "jlink", "raspberrypi-swd", "picoprobe"):
            if link not in upload_protocols or link in debug["tools"]:
                continue

            if link == "jlink":
                assert debug.get("jlink_device"), (
                    "Missed J-Link Device ID for %s" % board.id)
                debug["tools"][link] = {
                    "server": {
                        "package": "tool-jlink",
                        "arguments": [
                            "-singlerun",
                            "-if", "SWD",
                            "-select", "USB",
                            "-device", debug.get("jlink_device"),
                            "-port", "2331"
                        ],
                        "executable": ("JLinkGDBServerCL.exe"
                                       if platform.system() == "Windows" else
                                       "JLinkGDBServer")
                    },
                    "onboard": link in debug.get("onboard_tools", [])
                }
            else:
                openocd_target = debug.get("openocd_target")
                assert openocd_target, ("Missing target configuration for %s" %
                                        board.id)
                debug["tools"][link] = {
                    "server": {
                        "executable": "bin/openocd",
                        "package": "tool-openocd-rp2040-earlephilhower",
                        "arguments": [
                            "-s", "$PACKAGE_DIR/share/openocd/scripts",
                            "-f", "interface/%s.cfg" % link,
                            "-f", "target/%s" % openocd_target
                        ]
                    }
                }

        board.manifest["debug"] = debug
        return board

    def configure_debug_session(self, debug_config):
        adapter_speed = debug_config.speed or "1000"
        server_options = debug_config.server or {}
        server_arguments = server_options.get("arguments", [])
        if "interface/cmsis-dap.cfg" in server_arguments or "interface/picoprobe.cfg" in server_arguments:
            server_arguments.extend(
                ["-c", "adapter speed %s" % adapter_speed]
            )
        elif "jlink" in server_options.get("executable", "").lower():
            server_arguments.extend(
                ["-speed", adapter_speed]
            )
