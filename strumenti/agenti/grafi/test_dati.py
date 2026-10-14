import unittest

import numpy as np

import dati

PATCH = """diff --git a/pkg/mod.py b/pkg/mod.py
index 1..2 100644
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -4,3 +4,4 @@ class A:
     def f(self):
-        return 1
+        return 2
+
     def g(self):
@@ -11,1 +12,2 @@ def top():
     x = 1
+    y = 2
diff --git a/tests/test_mod.py b/tests/test_mod.py
--- a/tests/test_mod.py
+++ b/tests/test_mod.py
@@ -1,1 +1,2 @@
 import pkg
+import os
"""

SOURCE = """import os

class A:
    def f(self):
        return 1
    def g(self):
        return 3

@decorator
def top():
    x = 1
    return x
"""


CLASS_SOURCE = """import json


class JSONDecodeError(ValueError):
    def __init__(self, *args):
        ValueError.__init__(self, *args)


class HTTPError(Exception):
    pass
"""

NEW_METHOD = """--- a/pkg/exc.py
+++ b/pkg/exc.py
@@ -5,6 +5,9 @@ class JSONDecodeError(ValueError):
     def __init__(self, *args):
         ValueError.__init__(self, *args)

+    def __reduce__(self):
+        return ValueError.__reduce__(self)
+

 class HTTPError(Exception):
     pass
"""

BLANKS_AND_NEW_CLASS = """--- a/pkg/exc.py
+++ b/pkg/exc.py
@@ -4,5 +4,4 @@
 class JSONDecodeError(ValueError):
     def __init__(self, *args):
         ValueError.__init__(self, *args)
-

@@ -10,1 +9,4 @@ class HTTPError(Exception):
     pass
+
+class Other(Exception):
+    pass
"""


class TestPatch(unittest.TestCase):
    def test_parse_patch(self):
        out = dati.parse_patch(PATCH)
        self.assertEqual([h[:4] for h in out["pkg/mod.py"]], [(4, 3, 4, 4), (11, 1, 12, 2)])
        self.assertIn("tests/test_mod.py", out)
        self.assertEqual(dati.changed_lines(out["pkg/mod.py"]), ([5], [5, 13]))      # the blank '+' is left out

    def test_gold_locations(self):
        gold = dati.gold_locations(PATCH, lambda p: SOURCE if p == "pkg/mod.py" else None)
        self.assertEqual(gold["files"], ["pkg/mod.py"])
        self.assertEqual(gold["defs"], [("pkg.mod.A.f", "function"), ("pkg.mod.top", "function")])
        self.assertEqual(gold["module_level"], [])

    def test_new_method_counts_for_its_class(self):
        gold = dati.gold_locations(NEW_METHOD, lambda p: CLASS_SOURCE)
        self.assertEqual(gold["defs"], [("pkg.exc.JSONDecodeError", "class")])
        self.assertEqual(gold["module_level"], [])

    def test_blank_lines_and_new_classes(self):
        gold = dati.gold_locations(BLANKS_AND_NEW_CLASS, lambda p: CLASS_SOURCE)
        self.assertEqual(gold["unapplied"], [])
        self.assertEqual(gold["defs"], [])                         # a removed blank line changes nothing
        self.assertEqual(gold["module_level"], ["pkg/exc.py"])     # a new top-level class counts for the file

    def test_patch_that_does_not_apply(self):
        gold = dati.gold_locations(NEW_METHOD, lambda p: CLASS_SOURCE.replace("ValueError.__init__", "x"))
        self.assertEqual(gold["unapplied"], ["pkg/exc.py"])
        self.assertEqual(gold["module_level"], ["pkg/exc.py"])

    def test_library_only(self):
        patch = NEW_METHOD.replace("pkg/exc.py", "docs_src/exc.py")
        gold = dati.gold_locations(patch, lambda p: CLASS_SOURCE, "fastapi/fastapi")
        self.assertEqual(gold["files"], [])
        self.assertTrue(dati.in_library("src/requests/utils.py", "psf/requests"))
        self.assertFalse(dati.in_library("examples/table.py", "Textualize/rich"))

    def test_definitions_in_blocks_and_closures(self):
        src = ("try:\n    import simplejson\nexcept ImportError:\n    def loads(s):\n        return s\n\n"
               "if True:\n    class Proxy:\n        def get(self):\n            def inner():\n                return 1\n"
               "            return inner()\n\n"
               "def outer():\n    def helper():\n        return 2\n    return helper()\n")
        names = [d[0] for d in dati.definitions(src, "m")]
        self.assertEqual(names, ["m.loads", "m.Proxy", "m.Proxy.get", "m.outer"])     # no closures
        patch = "--- a/m.py\n+++ b/m.py\n@@ -16,1 +16,1 @@\n-        return 2\n+        return 3\n"
        self.assertEqual(dati.gold_locations(patch, lambda p: src)["defs"], [("m.outer", "function")])

    def test_deleted_file_counts_at_file_level(self):
        patch = "--- a/pkg/exc.py\n+++ /dev/null\n@@ -1,10 +0,0 @@\n" + "".join(
            "-" + line + "\n" for line in CLASS_SOURCE.splitlines())
        gold = dati.gold_locations(patch, lambda p: CLASS_SOURCE)
        self.assertEqual((gold["defs"], gold["deleted_files"], gold["module_level"]), ([], ["pkg/exc.py"],
                                                                                         ["pkg/exc.py"]))

    def test_new_file(self):
        patch = "--- /dev/null\n+++ b/pkg/new.py\n@@ -0,0 +1,2 @@\n+def f():\n+    pass\n"
        gold = dati.gold_locations(patch, lambda p: None)
        self.assertEqual((gold["files"], gold["new_files"], gold["defs"]), (["pkg/new.py"], ["pkg/new.py"], []))

    def test_match_kinds(self):
        modules = {"pkg.mod"}
        self.assertEqual(dati.match_kind("pkg.mod.A.f", "pkg.mod.A.f", modules), "exact")
        self.assertEqual(dati.match_kind("pkg.mod.A", "pkg.mod.A.f", modules), "container")
        self.assertEqual(dati.match_kind("pkg.mod.A.f", "pkg.mod.A", modules), "member")
        self.assertIsNone(dati.match_kind("pkg.mod", "pkg.mod.top", modules))
        gold = [("pkg.mod.A.f", "function")]
        self.assertEqual(dati.best_match_kind(["pkg.mod.A", "x"], gold, ["pkg/mod.py"]), "container")
        self.assertEqual(dati.best_match_kind(["pkg.mod.A", "pkg.mod.A.f"], gold, ["pkg/mod.py"]), "exact")
        self.assertEqual(dati.fn_hit_at(["pkg.mod.A"], gold, ["pkg/mod.py"], 5, exact=True), 0)
        self.assertEqual(dati.fn_hit_at(["pkg.mod.A"], gold, ["pkg/mod.py"], 5), 1)

    def test_module_name(self):
        self.assertEqual(dati.module_name("src/requests/models.py"), "requests.models")
        self.assertEqual(dati.module_name("rich/__init__.py"), "rich")

    def test_definitions_decorator_and_async(self):
        src = "@d\nasync def h():\n    pass\n"
        self.assertEqual(dati.definitions(src, "m"), [("m.h", "async", 1, 3)])


class TestText(unittest.TestCase):
    def test_anchors(self):
        text = "Calling `Client.send()` in httpx/_client.py fails; see build_request and MaxRetryError. It is bad."
        a = dati.anchors(text)
        self.assertIn("Client.send", a)
        self.assertIn("httpx/_client.py", a)
        self.assertIn("build_request", a)
        self.assertIn("MaxRetryError", a)
        self.assertNotIn("Calling", a)

    def test_tokens(self):
        self.assertEqual(dati.tokens("getResponseBody parse_header HTTPError"),
                         ["response", "body", "parse", "header", "http", "error"])


class TestRanking(unittest.TestCase):
    def test_bm25_prefers_matching_doc(self):
        bm = dati.BM25([["parse", "header"], ["send", "request"], ["parse", "body"]])
        s = bm.scores(["parse", "header"])
        self.assertEqual(int(np.argmax(s)), 0)

    def test_ppr_mass_near_seed(self):
        # chain 0-1-2-3, seed at 0: scores decrease with distance
        r = dati.personalized_pagerank(4, [(0, 1), (1, 2), (2, 3)], {0: 1.0})
        self.assertAlmostEqual(r.sum(), 1.0, places=6)
        self.assertTrue(r[0] > r[2] and r[1] > r[3])

    def test_split_is_stable(self):
        tasks = [{"repo": "a/x", "instance_id": f"x_{i}"} for i in range(9)] + \
                [{"repo": "b/y", "instance_id": f"y_{i}"} for i in range(3)]
        d1, t1 = dati.split_tasks(tasks)
        d2, t2 = dati.split_tasks(list(reversed(tasks)))
        self.assertEqual((d1, t1), (d2, t2))
        self.assertEqual(len(d1), 3 + 1)
        self.assertFalse(set(d1) & set(t1))

    def test_hit_and_recall(self):
        self.assertEqual(dati.hit_at(["a", "b", "c"], ["c"], 2), 0)
        self.assertEqual(dati.recall_at(["a", "b", "c"], ["a", "c"], 3), 1.0)
        self.assertIsNone(dati.hit_at(["a"], [], 1))


if __name__ == "__main__":
    unittest.main()
