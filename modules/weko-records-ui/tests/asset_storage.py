"""Collect real assets into a new, independently owned test directory."""

import os

from flask_collect.storage.link import Storage as LinkStorage


class Storage(LinkStorage):
    """Avoid resolving link targets when every destination is new.

    Keep the upstream blueprint iterator and its filtering/precedence rules.
    Existing roots or conflicting destinations use the upstream implementation.
    """

    def run(self):
        if os.path.lexists(self.collect.static_root):
            return super().run()

        self.log("Collect static from blueprints")
        directories = set()
        total = 0
        for blueprint, source, relative in self:
            destination = os.path.join(self.collect.static_root, relative)
            if os.path.lexists(destination):
                return super().run()
            directory = os.path.dirname(destination)
            if directory not in directories:
                os.makedirs(directory, exist_ok=True)
                directories.add(directory)
            os.symlink(source, destination)
            self.log("{0}:{1} symbolink link created".format(blueprint.name, relative))
            total += 1
        self.log("0 of {0} files already present".format(total))
        self.log("Done collecting.")
