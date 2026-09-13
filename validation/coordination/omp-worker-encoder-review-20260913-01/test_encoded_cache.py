"""Pure tests for the encoded() cache assessment (run on WSL Python 3.10).

No worker/Model import; the extracted function comes from the pinned archived
snapshot.  Standard library only.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import assess_encoded_cache as assess  # noqa: E402

SOURCE = assess.DEFAULT_SOURCE


class EncodedCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = SOURCE.read_bytes()
        # keep the function off the instance protocol: class attribute access
        # would bind it as a method; always call through the class
        cls.encoded = staticmethod(
            assess.extract_encoded(source)[0]).__func__
        cls.tree = assess.extract_encoded(source)[1]

    def real(self, payload):
        return type(self).encoded(payload)

    def test_extracted_encoded_is_real_dumps_one_liner(self):
        payload = assess.representative_payloads()["request"]
        self.assertEqual(self.real(payload),
                         json.dumps(payload, separators=(",", ":"),
                                    allow_nan=False))

    def test_byte_equivalence_on_representative_shapes(self):
        for name, payload in assess.representative_payloads().items():
            with self.subTest(payload=name):
                self.assertEqual(self.real(payload),
                                 assess.candidate_encoded(payload))

    def test_exception_equivalence(self):
        for name, payload in assess.exception_battery().items():
            with self.subTest(payload=name):
                original = assess._outcome(type(self).encoded, payload)
                candidate = assess._outcome(assess.candidate_encoded, payload)
                self.assertEqual(original, candidate)
                self.assertEqual(original[0],
                                 "TypeError" if name == "tuple_key"
                                 else "ValueError")

    def test_shared_encoder_under_threads(self):
        outcome = assess.threading_check(type(self).encoded)
        self.assertEqual(outcome["divergences"], 0)

    def test_call_site_census_matches_loop_paths(self):
        census = assess.call_site_census(self.tree)
        # supervisor frame build + worker step/initial paths, static count
        self.assertEqual(census.get("receive_workers"), 1)
        self.assertEqual(census.get("_worker_loop"), 5)

    def test_module_and_model_never_imported(self):
        self.assertNotIn("worker", sys.modules)
        self.assertNotIn("Simulator.wksim_core.worker", sys.modules)


if __name__ == "__main__":
    unittest.main()
