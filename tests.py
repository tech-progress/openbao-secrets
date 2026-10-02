import unittest
from app import canonical_path, data_plane_path


class RoutingTests(unittest.TestCase):
    def test_operator_paths_not_public(self):
        for path in ["/v1/sys/init", "/v1/sys/unseal", "/v1/sys/storage/raft/snapshot", "/v1/auth/token/create", "/v1/secret", "/v1/transit"]:
            self.assertFalse(data_plane_path(path))

    def test_data_plane_allowlist(self):
        for path in ["/v1/secret/data/example", "/v1/transit/encrypt/example", "/v1/auth/approle/login"]:
            self.assertTrue(data_plane_path(path))

    def test_canonical_paths(self):
        self.assertEqual(canonical_path("/v1/secret/data/name?version=1"), "/v1/secret/data/name")
        for target in ["https://other/v1/sys/init", "//v1/sys/init", "/v1/secret/../sys/init", "/v1/secret/%2e%2e/sys/init", "/v1/%2573ys/init", "/v1/secret\\sys/init", "/v1/sys/init#ignored"]:
            with self.assertRaises(ValueError):
                canonical_path(target)


if __name__ == "__main__":
    unittest.main()
