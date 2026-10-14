import json
import unittest

import numpy as np

import agente_grafi as A

FILES = {"pkg/__init__.py": "", "pkg/mod.py": "def f():\n    return g()\n\ndef g():\n    return 1\n",
         "pkg/sub/other.py": "class C:\n    def m(self):\n        pass\n", "README.md": "hello\n"}
GRAPH = {"ids": ["pkg.mod.f", "pkg.mod.g", "pkg.sub.other.C", "pkg.sub.other.C.m"],
         "text": {"pkg.mod.f": "def f():\n    return g()", "pkg.mod.g": "def g():\n    return 1",
                  "pkg.sub.other.C": "class C: ...", "pkg.sub.other.C.m": "def m(self): pass"},
         "out": {"pkg.mod.f": [("pkg.mod.g", "CALLS")], "pkg.sub.other.C": [("pkg.sub.other.C.m", "DEFINES")]},
         "inc": {"pkg.mod.g": [("pkg.mod.f", "CALLS")], "pkg.sub.other.C.m": [("pkg.sub.other.C", "DEFINES")]}}
EMB = {"pkg.mod.f": np.array([1.0, 0.0]), "pkg.mod.g": np.array([0.9, 0.1]),
       "pkg.sub.other.C.m": np.array([0.0, 1.0])}


def load(s):
    return json.loads(s)


class TestTools(unittest.TestCase):
    def setUp(self):
        self.repo = A.Repo(FILES, GRAPH, EMB)

    def test_list_files(self):
        out = load(self.repo.list_files(".", 1))
        self.assertEqual(out["entries"], ["README.md", "pkg/"])
        out = load(self.repo.list_files("pkg", 1))
        self.assertIn("pkg/sub/", out["entries"])

    def test_search_code(self):
        out = load(self.repo.search_code("return g()"))
        self.assertEqual(out["matches"], ["pkg/mod.py:2: return g()"])
        self.assertEqual(load(self.repo.search_code("("))["status"], "ok")
        self.assertEqual(load(self.repo.search_code("(", regex=True))["status"], "error")

    def test_read_file(self):
        out = load(self.repo.read_file("/workspace/pkg/mod.py", 2, 3))
        self.assertEqual(out["content"], "    return g()\n")
        self.assertEqual(out["total_lines"], 5)
        self.assertEqual(load(self.repo.read_file("../x.py"))["status"], "error")

    def test_resolve_tiers(self):
        self.assertEqual(self.repo.resolve("pkg.mod.f"), "pkg.mod.f")
        self.assertEqual(self.repo.resolve("C.m"), "pkg.sub.other.C.m")
        self.assertEqual(self.repo.resolve("PKG.MOD.G"), "pkg.mod.g")
        self.assertEqual(self.repo.resolve("other.C"), "pkg.sub.other.C")
        self.assertIsNone(self.repo.resolve("nothing"))

    def test_neighbors_and_subgraph(self):
        out = load(self.repo.get_code_neighbors("g"))
        self.assertEqual(out["node"], "pkg.mod.g")
        self.assertEqual(out["neighbors"], ["pkg.mod.f"])
        sub = load(self.repo.get_code_subgraph(["f", "g"]))
        self.assertEqual(sub["edges"], [{"from": "pkg.mod.f", "to": "pkg.mod.g", "type": "CALLS"}])

    def test_similar_code_needs_a_symbol(self):
        self.assertEqual(load(self.repo.search_similar_code("return a number"))["count"], 0)
        out = load(self.repo.search_similar_code("f", k=2))
        self.assertEqual([r["node_name"] for r in out["results"]], ["pkg.mod.f", "pkg.mod.g"])

    def test_run_task_with_fake_model(self):
        script = iter([
            {"message": {"content": "", "tool_calls": [{"function": {"name": "search_code",
                                                                     "arguments": {"pattern": "def g"}}}]}},
            {"message": {"content": "", "tool_calls": [{"function": {"name": "submit_locations", "arguments": {
                "locations": ["pkg/mod.py::g"]}}}]}},
        ])
        task = {"instance_id": "x_1", "repo": "o/x", "problem_statement": "g returns 1", "hints_text": ""}
        out = A.run_task(task, self.repo, "none", chat=lambda sent, tools: next(script))
        self.assertEqual(out["submitted"], ["pkg/mod.py::g"])
        self.assertEqual(out["calls"], 2)
        self.assertIsNone(out["infra_error"])


TASK = {"instance_id": "x_1", "repo": "o/x", "problem_statement": "g returns 1", "hints_text": ""}
SEARCH = {"message": {"content": "", "tool_calls": [{"function": {"name": "search_code",
                                                                  "arguments": {"pattern": "def g"}}}]}}
SUBMIT = {"message": {"content": "", "tool_calls": [{"function": {"name": "submit_locations",
                                                                  "arguments": {"locations": ["pkg/mod.py::g"]}}}]}}


class TestLoop(unittest.TestCase):
    def setUp(self):
        self.repo = A.Repo(FILES, GRAPH, EMB)

    def test_budget_warning(self):
        base = A.ok(x=1)
        self.assertNotIn("budget_warning", load(A.with_budget_warning(base, 9, 20)))
        self.assertIn("Only 10 tool call(s) remaining (10/20 used)", load(A.with_budget_warning(base, 10, 20))["budget_warning"])
        self.assertNotIn("budget_warning", load(A.with_budget_warning(base, 9, 10)))

    def test_forced_submit_after_the_budget(self):
        seen_tools = []

        def chat(sent, tools):
            seen_tools.append([t["function"]["name"] for t in tools])
            return SUBMIT if len(seen_tools) > 3 else SEARCH
        out = A.run_task(TASK, self.repo, "none", chat=chat, max_calls=3)
        self.assertEqual(out["calls"], 3)
        self.assertEqual(out["end"], "budget")
        self.assertTrue(out["forced_submit"])
        self.assertEqual(out["submitted"], ["pkg/mod.py::g"])
        self.assertEqual(seen_tools[-1], ["submit_locations"])

    def test_nudges_cost_no_calls(self):
        script = iter([{"message": {"content": ""}}, {"message": {"content": "I think it is g."}}, SUBMIT])
        out = A.run_task(TASK, self.repo, "none", chat=lambda sent, tools: next(script))
        users = [m["content"] for m in out["messages"] if m["role"] == "user"][1:]
        self.assertEqual(users, [A.NUDGE_EMPTY, A.NUDGE_TEXT])
        self.assertEqual((out["calls"], out["turns"], out["nudges"], out["end"]), (1, 3, 2, "submitted"))

    def test_four_silent_turns_end_the_exploration(self):
        replies = [{"message": {"content": ""}}, SEARCH] + [{"message": {"content": ""}}] * 4 + [SUBMIT]
        script = iter(replies)
        out = A.run_task(TASK, self.repo, "none", chat=lambda sent, tools: next(script))
        self.assertEqual(out["end"], "nudges")                      # the counter restarted after the search
        self.assertEqual((out["calls"], out["nudges"]), (1, 4))
        self.assertTrue(out["forced_submit"])
        self.assertEqual(out["submitted"], ["pkg/mod.py::g"])

    def test_fit_context_keeps_issue_and_recent_outputs(self):
        sent = [{"role": "system", "content": "s" * 300}, {"role": "user", "content": "issue " * 500}]
        for i in range(8):
            sent += [{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "read_file"}}]},
                     {"role": "tool", "content": str(i) * 9000}]
        before = [dict(m) for m in sent]
        replaced = A.fit_context(sent)
        tools = [m for m in sent if m["role"] == "tool"]
        self.assertEqual(sent[:2], before[:2])
        self.assertEqual([m["content"] for m in tools[-5:]], [str(i) * 9000 for i in range(3, 8)])
        self.assertEqual(replaced, 3)
        self.assertTrue(all(m["content"] == A.STUB for m in tools[:3]))
        self.assertEqual(A.fit_context(sent), 0)                    # nothing left to replace

    def test_fit_context_leaves_short_talks_alone(self):
        sent = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
                {"role": "tool", "content": "x" * 100}]
        self.assertEqual(A.fit_context(sent), 0)
        self.assertEqual(sent[2]["content"], "x" * 100)

    def test_location_node_and_hit(self):
        self.assertEqual(A.location_node("src/requests/utils.py::get_netrc_auth"), "requests.utils.get_netrc_auth")
        self.assertEqual(A.location_node("/workspace/pkg/mod.py::C.m"), "pkg.mod.C.m")
        self.assertEqual(A.location_node("pkg/mod.py::C.m()"), "pkg.mod.C.m")
        self.assertEqual(A.location_node("pkg/mod.py::f(x, y)"), "pkg.mod.f")
        hit = A.agent_hit(["pkg/mod.py"], [("pkg.mod.g", "function")], ["pkg/mod.py"])
        self.assertEqual(hit, {"fn": 0, "fn_exact": 0, "fn_exact_raw": 0, "kind": None, "file": 1})
        hit = A.agent_hit(["pkg/sub/other.py::C"], [("pkg.sub.other.C.m", "function")], ["pkg/sub/other.py"])
        self.assertEqual(hit, {"fn": 1, "fn_exact": 0, "fn_exact_raw": 0, "kind": "container", "file": 1})
        hit = A.agent_hit(["`pkg.mod.g`"], [("pkg.mod.g", "function")], ["pkg/mod.py"], FILES)
        self.assertEqual(hit, {"fn": 1, "fn_exact": 1, "fn_exact_raw": 1, "kind": "exact", "file": 1})

    def test_names_completed_inside_their_file(self):
        gold = [("pkg.sub.other.C.m", "function")]
        hit = A.agent_hit(["pkg/sub/other.py::m"], gold, ["pkg/sub/other.py"], FILES)
        self.assertEqual((hit["fn_exact"], hit["fn_exact_raw"]), (1, 0))
        self.assertEqual(A.resolve_in_file("pkg.sub.other.m", FILES), "pkg.sub.other.C.m")      # dotted id too
        self.assertEqual(A.resolve_in_file("pkg/mod.py::nothing", FILES), "pkg.mod.nothing")
        two = dict(FILES, **{"pkg/two.py": "class A:\n    def m(self):\n        pass\n\n"
                                            "class B:\n    def m(self):\n        pass\n"})
        self.assertEqual(A.resolve_in_file("pkg/two.py::m", two), "pkg.two.m")                   # ambiguous: no completion

    def test_workspace_layout_and_root_names(self):
        self.assertEqual(A.workspace_layout(FILES), "README.md\npkg/")
        task = {"instance_id": "x_1", "repo": "o/x", "problem_statement": "p", "hints_text": ""}
        self.assertIn("## Workspace Layout", A.first_message(task, "none", None, "README.md\npkg/"))
        repo = A.Repo(FILES, GRAPH, EMB, root_names=("o/x",))
        for path in ("o/x", "/workspace", "/workspace/", ".", ""):
            self.assertEqual(load(repo.list_files(path, 1))["entries"], ["README.md", "pkg/"], path)
        self.assertEqual(load(repo.list_files("/workspace/pkg", 1))["count"], 3)

    def test_graph_tools_translate_only_our_location_format(self):
        self.assertEqual(A.normalize_symbol("pkg/mod.py::g"), "pkg.mod.g")
        self.assertEqual(A.normalize_symbol("pkg/mod.py"), "pkg/mod.py")
        self.assertEqual(A.normalize_symbol("`g`"), "`g`")

    def test_slow_regex_is_stopped_or_fast(self):
        repo = A.Repo({"a.py": "a" * 400 + "!\n"}, GRAPH, EMB)
        self.assertEqual(load(repo.search_code(r"(a+)+$", regex=True))["status"], "ok")
        slow = A.Repo({"b.py": "a" * 80 + "\n"}, GRAPH, EMB)
        old, A.REGEX_SECONDS = A.REGEX_SECONDS, 0.2
        try:
            out = load(slow.search_code(r"((a|aa|aaa)+)+b", regex=True))
        finally:
            A.REGEX_SECONDS = old
        self.assertEqual(out["error_type"], "Timeout")

    def test_names_inside_functions_and_root_paths(self):
        files = {"pkg/h.py": "def handler():\n    def app():\n        return 1\n    return app\n"}
        self.assertEqual(A.resolve_in_file("pkg/h.py::handler.app", files), "pkg.h.handler")
        self.assertEqual(A.resolve_in_file("pkg/sub/other.py::C.nothing", FILES), "pkg.sub.other.C.nothing")
        repo = A.Repo(FILES, GRAPH, EMB, root_names=("o/x",))
        self.assertEqual(load(repo.list_files("/workspace/o/x", 1))["entries"], ["README.md", "pkg/"])
        self.assertEqual(load(repo.list_files("o/x/pkg", 1))["count"], 3)

    def test_snapshot_keeps_hidden_folders(self):
        import io
        import tarfile
        import tempfile
        import istantanee
        with tempfile.TemporaryDirectory() as tmp:
            path = tmp + "/s.tgz"
            with tarfile.open(path, "w:gz") as tar:
                for name in ("./.github/w.yml", "./pkg/a.py", "./.git/config.txt"):
                    data = b"x = 1\n"
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
            self.assertEqual(sorted(istantanee.read_snapshot(path)), [".github/w.yml", "pkg/a.py"])

    def test_read_file_truncation_flag(self):
        repo = A.Repo(FILES, GRAPH, EMB)
        self.assertFalse(load(repo.read_file("pkg/mod.py", 1, 99))["is_truncated"])

    def test_location_forms(self):
        self.assertEqual(A.split_location("./pkg/mod.py:g"), ("pkg/mod.py", "g"))
        self.assertEqual(A.split_location("pkg/mod.py:120"), ("pkg/mod.py", ""))
        self.assertEqual(A.split_location("'pkg/mod.py::C.m (the method)'"), ("pkg/mod.py", "C.m"))
        self.assertEqual(A.location_file("requests/utils.py::f", {"src/requests/utils.py": ""}),
                         "src/requests/utils.py")
        self.assertEqual(A.location_file("pkg.sub.other.C.m", FILES), "pkg/sub/other.py")
        self.assertEqual(A.submission({"locations": "a.py::f, b.py::g(x, y)"}), ["a.py::f", "b.py::g(x, y)"])
        self.assertEqual(A.submission({"locations": [{"path": "a.py"}, 3]}), ['{"path": "a.py"}', "3"])
        self.assertEqual(A.submission("not a dict"), [])

    def test_malformed_arguments_never_crash(self):
        repo = A.Repo(FILES, GRAPH, EMB)
        for name, args in [("list_files", {"path": None}), ("get_code_neighbors", {"node": "g", "edge_type": 3}),
                           ("read_file", ["pkg/mod.py"]), ("read_file", {"filepath": "pkg/mod.py", "start_line": {}}),
                           ("search_code", {"pattern": "(a+)+$" * 40, "regex": True}), ("nope", {})]:
            out = load(repo.call(name, args))
            self.assertIn(out["status"], ("ok", "error"), (name, args))
        self.assertEqual(load(repo.call("get_code_neighbors", {"node": "pkg/mod.py::g"}))["node"], "pkg.mod.g")
        self.assertEqual(load(repo.call("search_similar_code", {"query": "pkg/mod.py::f"}))["count"], 3)


class TestLibrary(unittest.TestCase):
    def test_keep_library(self):
        import localizza
        files = {"fastapi/routing.py": "", "tests/test_mod.py": "", "docs_src/app.py": "",
                 "fastapi/conftest.py": ""}
        ranking = ["tests.test_mod.test_f", "fastapi.routing.f", "docs_src.app.main", "tutorial001.main",
                   "fastapi.conftest.fixture"]
        self.assertEqual(localizza.keep_library(ranking, files, "fastapi/fastapi"), ["fastapi.routing.f"])

    def test_issue_text_and_project_anchor(self):
        import localizza
        task = {"repo": "fastapi/fastapi", "problem_statement": "FastAPI breaks <!-- template --> in `get_x` "
                "see https://github.com/x/y?a=b", "hints_text": ""}
        text = localizza.issue_text(task)
        self.assertNotIn("github", text)
        self.assertNotIn("template", text)
        graph = {"ids": ["fastapi.applications.FastAPI", "fastapi.utils.get_x"],
                 "text": {"fastapi.applications.FastAPI": "", "fastapi.utils.get_x": ""}, "out": {}, "inc": {}}
        self.assertEqual(localizza.rank_anchors(graph, task), ["fastapi.utils.get_x"])

    def test_degree_power_lowers_hubs(self):
        import localizza
        ids = ["hub", "a", "b", "c", "d", "leaf"]
        graph = {"ids": ids, "text": {i: "" for i in ids},
                 "out": {"hub": [("a", "calls"), ("b", "calls"), ("c", "calls"), ("d", "calls")],
                         "a": [("leaf", "calls")]}, "inc": {}}
        self.assertEqual(localizza.rank_graph(graph, ["a"], 0.5)[1], "hub")
        self.assertEqual(localizza.rank_graph(graph, ["a"], 0.5, degree_power=1.0)[1], "leaf")


if __name__ == "__main__":
    unittest.main()
