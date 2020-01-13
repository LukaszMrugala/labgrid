# pylint: disable=no-member
import enum
import logging
import os
import time
import attr

from ..factory import target_factory
from ..step import step
from ..util.managedfile import ManagedFile
from .common import Driver
from ..driver.exception import ExecutionError

from ..util.helper import processwrapper
from ..util import Timeout


class Mode(enum.Enum):
    DD = 1
    BMAPTOOL = 2


@target_factory.reg_driver
@attr.s(eq=False)
class NetworkUSBStorageDriver(Driver):
    bindings = {
        "storage": {
            "USBMassStorage",
            "NetworkUSBMassStorage",
            "USBSDMuxDevice",
            "NetworkUSBSDMuxDevice"
        },
    }
    image = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(str))
    )

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.logger = logging.getLogger("{}:{}".format(self, self.target))

    def on_activate(self):
        pass

    def on_deactivate(self):
        pass

    @Driver.check_active
    @step(args=['filename'])
    def write_image(self, filename=None, mode=Mode.DD):
        if filename is None and self.image is not None:
            filename = self.target.env.config.get_image_path(self.image)
        assert filename, "write_image requires a filename"
        mf = ManagedFile(filename, self.storage)
        mf.sync_to_resource()
        self.logger.info("pwd: %s", os.getcwd())

        # wait for medium
        timeout = Timeout(10.0)
        while not timeout.expired:
            try:
                if self.get_size() > 0:
                    break
                time.sleep(0.5)
            except ValueError:
                # when the medium gets ready the sysfs attribute is empty for a short time span
                continue
        else:
            raise ExecutionError("Timeout while waiting for medium")

        if mode == Mode.DD:
            args = [
                "dd",
                "if={}".format(mf.get_remote_path()),
                "of={}".format(self.storage.path),
                "status=progress",
                "bs=4M",
                "conv=fdatasync"
            ]
        elif mode == Mode.BMAPTOOL:
            args = [
                "bmaptool",
                "copy",
                "{}".format(mf.get_remote_path()),
                "{}".format(self.storage.path),
            ]
        else:
            raise ValueError

        processwrapper.check_output(
            self.storage.command_prefix + args
        )

    @Driver.check_active
    @step(result=True)
    def get_size(self):
        args = ["cat", "/sys/class/block/{}/size".format(self.storage.path[5:])]
        size = processwrapper.check_output(self.storage.command_prefix + args)
        return int(size)
