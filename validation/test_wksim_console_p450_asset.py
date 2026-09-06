"""Controlled, in-memory P450 parsing/conversion tests (no UE or builds)."""
import importlib.util
import io
import math
from pathlib import Path
import struct
import unittest
from unittest.mock import patch, MagicMock

SPEC = importlib.util.spec_from_file_location("p450_asset", Path(__file__).resolve().parents[1] / "tools/prepare_p450_asset.py")
asset = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(asset)
TRIANGLE = ((1., 2., 3.), (2., 2., 3.), (1., 3., 3.))


def binary(triangle=TRIANGLE):
    return b"solid binary".ljust(80, b"\0") + struct.pack("<I12fH", 1, 0, 0, 1, *sum(triangle, ()), 0)


def ascii_stl():
    return b"solid test\nfacet normal 0 0 1\nouter loop\nvertex 1 2 3\nvertex 2 2 3\nvertex 1 3 3\nendloop\nendfacet\nendsolid test\n"


class P450AssetTests(unittest.TestCase):
    def response(self, data):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.geturl.return_value = asset.MESH_URLS["meshes/p450.stl"]
        response.headers = {"Content-Length": str(len(data))}
        response.read1.side_effect = io.BytesIO(data).read1
        return response

    def test_fetch_verified_bytes(self):
        data = binary()
        response = self.response(data)
        with patch.object(asset.urllib.request, "build_opener") as build, patch.dict(asset.SOURCES, {"meshes/p450.stl": asset.blob_sha1(data)}):
            build.return_value.open.return_value = response
            self.assertEqual(asset.fetch_mesh("meshes/p450.stl"), data)
            self.assertEqual(build.return_value.open.call_args.kwargs["timeout"], 10)

    def test_fetch_mismatch(self):
        with patch.object(asset.urllib.request, "build_opener") as build:
            build.return_value.open.return_value = self.response(binary())
            with self.assertRaisesRegex(ValueError, "blob mismatch"):
                asset.fetch_mesh("meshes/p450.stl")

    def test_fetch_network_failure(self):
        with patch.object(asset.urllib.request, "build_opener") as build:
            build.return_value.open.side_effect = TimeoutError("controlled timeout")
            with self.assertRaises(TimeoutError):
                asset.fetch_mesh("meshes/p450.stl")

    def test_fetch_size_deadline_and_truncation(self):
        for mode in ("declared", "stream", "truncated", "deadline", "redirect"):
            with self.subTest(mode=mode), patch.object(asset.urllib.request, "build_opener") as build:
                response = self.response(binary())
                build.return_value.open.return_value = response
                if mode == "declared":
                    response.headers = {"Content-Length": str(asset.MAX_BYTES+1)}
                elif mode == "stream":
                    response.headers = {}
                elif mode == "truncated":
                    response.headers = {"Content-Length": "200"}
                elif mode == "redirect":
                    response.geturl.return_value = "https://example.com/other"
                with patch.object(asset, "MAX_BYTES", 100 if mode == "stream" else asset.MAX_BYTES), patch.object(asset.time, "monotonic", side_effect=[0, 46] if mode == "deadline" else lambda: 0):
                    with self.assertRaises((ValueError, TimeoutError)):
                        asset.fetch_mesh("meshes/p450.stl")

    def test_redirect_handler_and_allowlist(self):
        with self.assertRaises(ValueError):
            asset.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com")
        with patch.object(asset.urllib.request, "build_opener") as build:
            for name in ("LICENSE", "meshes/other.stl", "../p450.stl"):
                with self.assertRaises(ValueError):
                    asset.fetch_mesh(name)
            build.assert_not_called()

    def test_offline_and_nonmesh_missing_never_fetch(self):
        for relative, opt_in in (("meshes/p450.stl", False), ("LICENSE", True)):
            with patch.object(asset, "git_read", return_value=f"{asset.SOURCES[relative]} missing\n".encode()), patch.object(asset, "fetch_mesh") as fetch:
                with self.assertRaisesRegex(ValueError, "local Git blob missing"):
                    asset.read_source(Path("."), relative, opt_in)
                fetch.assert_not_called()

    def test_only_missing_blob_uses_opt_in(self):
        name = "meshes/p450.stl"
        with patch.object(asset, "git_read", return_value=f"{asset.SOURCES[name]} missing\n".encode()), patch.object(asset, "fetch_mesh", return_value=b"verified") as fetch:
            self.assertEqual(asset.read_source(Path("."), name, True), (b"verified", asset.MESH_URLS[name]))
            fetch.assert_called_once_with(name)
        with patch.object(asset, "git_read", side_effect=ValueError("repository failure")), patch.object(asset, "fetch_mesh") as fetch:
            with self.assertRaises(ValueError):
                asset.read_source(Path("."), name, True)
            fetch.assert_not_called()

    def test_binary_solid_header(self):
        self.assertEqual(asset.parse_stl(binary()), ([TRIANGLE], "binary"))

    def test_ascii_equivalence(self):
        self.assertEqual(asset.parse_stl(ascii_stl()), ([TRIANGLE], "ascii"))

    def test_invalid_binary_lengths(self):
        for data in (binary()[:-1], binary() + b"x", b"\0"*84):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                asset.parse_stl(data)

    def test_nonfinite(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                asset.parse_stl(binary(((value, 2, 3), *TRIANGLE[1:])))
        with self.assertRaises(ValueError):
            asset.parse_stl(ascii_stl().replace(b"vertex 1 2", b"vertex nan 2"))

    def test_degenerate(self):
        triangle = (TRIANGLE[0],)*3
        self.assertEqual(asset.parse_stl(binary(triangle)), ([triangle], "binary"))
        obj, _ = asset.convert_obj([triangle, TRIANGLE], "test")
        self.assertIn(b"f 1 2 3\n", obj)
        self.assertIn(b"f 4//1 5//1 6//1\n", obj)
        self.assertEqual(obj.count(b"vn "), 1)

    def test_ascii_grammar(self):
        for data in (ascii_stl().replace(b"endloop", b"bad"),
                     ascii_stl().replace(b"vertex 2 2 3\n", b""),
                     ascii_stl()+b"garbage", b"solid x\nendsolid x"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                asset.parse_stl(data)

    def test_frame_winding_normal_and_origin(self):
        data, bounds = asset.convert_obj([TRIANGLE], "test.stl")
        lines = data.decode().splitlines()
        vertices = [tuple(map(float, line.split()[1:])) for line in lines if line.startswith("v ")]
        self.assertEqual(vertices, [(100, -200, 300), (100, -300, 300), (200, -200, 300)])
        self.assertIn("vn 0 0 1", lines)
        self.assertIn("f 1//1 2//1 3//1", lines)
        self.assertEqual(bounds, {"min": [100, -300, 300], "max": [200, -200, 300], "size": [100, 100, 0]})
        self.assertEqual(asset.normal(vertices), (0, 0, 1))

    def test_determinism(self):
        self.assertEqual(asset.convert_obj([TRIANGLE]*2, "test"), asset.convert_obj([TRIANGLE]*2, "test"))

    def test_refuses_existing_output_without_git(self):
        with patch.object(asset, "git_read") as git:
            with self.assertRaises(FileExistsError):
                asset.prepare(Path("."), Path(__file__).parent)
            git.assert_not_called()

    def test_wrong_blob_rejected_before_output(self):
        with patch.object(asset, "git_read", return_value=b"wrong"), patch.object(Path, "exists", return_value=False), patch.object(Path, "mkdir") as mkdir:
            with self.assertRaises(ValueError):
                asset.prepare(Path("."), Path("unused"))
            mkdir.assert_not_called()

    def test_git_failure_is_offline_and_actionable(self):
        error = asset.subprocess.CalledProcessError(128, ["git"], stderr=b"missing object")
        with patch.object(asset.subprocess, "run", side_effect=error) as run:
            with self.assertRaisesRegex(ValueError, "automatic fetching disabled.*missing object"):
                asset.git_read(Path("."), "cat-file", "-s", "missing")
            self.assertEqual(run.call_args.kwargs["env"]["GIT_NO_LAZY_FETCH"], "1")

    def test_sdf_metadata(self):
        data = b'''<sdf><model><link name="rotor_0"><pose>1 2 3 0 0 0</pose><visual name="v"><pose>0 0 0 0 0 0</pose><geometry><mesh><scale>1 1 1</scale><uri>model://p450/meshes/p450_ccw.stl</uri></mesh></geometry></visual></link><plugin><turningDirection>ccw</turningDirection><linkName>rotor_0</linkName><jointName>j</jointName><motorNumber>0</motorNumber></plugin></model></sdf>'''
        rotor = asset.sdf_metadata(data)["rotors"][0]
        self.assertEqual(rotor["ue_translation_cm_unapplied"], (100, -200, 300))
        self.assertEqual(rotor["source_turning_direction"], "ccw")
        with self.assertRaises(ValueError):
            asset.sdf_metadata(data.replace(b"1 1 1", b"100 100 100"))


if __name__ == "__main__":
    unittest.main()
