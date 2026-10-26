from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aperio.mesh import MeshError, MeshStore
from aperio.store import Project


class MeshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-mesh-")
        self.root = Path(self.temp.name)
        self.project = Project.init(self.root, name="mesh-test")
        self.store = MeshStore(self.project)

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_send_read_ack_and_reply(self) -> None:
        first = self.store.send("builder", "reviewer", "Please review task A", task_id="task-a", kind="task")
        self.assertEqual(first["sender"], "builder")
        self.assertEqual(first["recipient"], "reviewer")
        messages = self.store.read(recipient="reviewer", mark_read=True)
        self.assertEqual(len(messages), 1)
        self.assertIsNotNone(messages[0]["read_at"])
        reply = self.store.reply(first["id"], "reviewer", "Reviewed: confirmed")
        self.assertEqual(reply["thread_id"], first["thread_id"])
        self.assertEqual(reply["recipient"], "builder")
        acked = self.store.ack(first["id"], "reviewer")
        self.assertIsNotNone(acked["ack_at"])
        self.assertIsNotNone(acked["read_at"])
        self.assertEqual(self.store.stats()["messages"], 2)

    def test_recipient_and_task_filters(self) -> None:
        self.store.send("builder", "reviewer", "one", task_id="task-a")
        self.store.send("builder", "other", "two", task_id="task-b")
        self.assertEqual(len(self.store.read(recipient="reviewer")), 1)
        self.assertEqual(len(self.store.read(task_id="task-b")), 1)
        self.assertEqual(len(self.store.read(thread_id="does-not-exist")), 0)

    def test_restart_persistence(self) -> None:
        sent = self.store.send("builder", "reviewer", "persist me")
        self.store.close()
        self.store = MeshStore(self.project)
        messages = self.store.read(recipient="reviewer")
        self.assertEqual([m["id"] for m in messages], [sent["id"]])
        self.assertEqual(messages[0]["body"], "persist me")

    def test_unknown_message_ack_fails(self) -> None:
        with self.assertRaises(MeshError):
            self.store.ack(9999, "reviewer")

    def test_empty_message_is_refused(self) -> None:
        with self.assertRaises(MeshError):
            self.store.send("builder", "reviewer", "   ")


if __name__ == "__main__":
    unittest.main()
