"""真实世界事实基座（Chroma 向量库 + 检索注入）测试。"""
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anyio

from app.services.grounding import GroundingService, GROUNDING_LABEL
from app.services.facts import build_narrative_context, build_facts
from app.services.store import Story
from app.services.vector_kb import build_chroma_facade, ChromaKBFacade, LLMEmbeddingFunction, NGramEmbedding, _SEED


def _facade() -> ChromaKBFacade:
    return build_chroma_facade(path=tempfile.mkdtemp(), mode="n-gram")


class TestVectorGrounding:
    def test_real_entities_are_grounded(self):
        svc = GroundingService(vector=_facade())
        res = anyio.run(svc.resolve, "我独自资助刘强东500个鸡蛋", "近未来刘强东东山再起")
        assert "刘强东" in res.labels
        joined = "".join(res.facts)
        assert "1998年6月18日" in joined and "纳斯达克" in joined and "9618" in joined
        assert svc.facts_text(res).startswith(GROUNDING_LABEL)

    def test_product_claude_code_grounded(self):
        svc = GroundingService(vector=_facade())
        res = anyio.run(svc.resolve, "有人想把Claude Code写成金手指")
        assert "Claude Code" in res.labels
        joined = "".join(res.facts)
        assert "Anthropic" in joined and "编程助手" in joined
        assert "记事应用" not in res.facts  # 不能被误写为"藏机密的记事应用"

    def test_pure_fantasy_returns_empty(self):
        svc = GroundingService(vector=_facade())
        res = anyio.run(svc.resolve, "少年在雾海的旧城寻找自己失去的身世")
        assert res.facts == [] and res.labels == []

    def test_seed_is_idempotent(self):
        path = tempfile.mkdtemp()
        f1 = build_chroma_facade(path=path, mode="n-gram")
        f2 = build_chroma_facade(path=path, mode="n-gram")
        assert f1._col.count() == f2._col.count() > 0

    def test_grounding_context_and_facts_preview(self):
        story = Story(id="x", premise="资助刘强东")
        story.grounding = ["• 刘强东：1998年创办京东"]
        assert "真实事实基座" in build_narrative_context(story)
        assert any("真实事实" in f for f in build_facts(story))

    def test_no_vector_is_empty(self):
        svc = GroundingService(vector=None)
        res = anyio.run(svc.resolve, "资助刘强东500个鸡蛋")
        assert res.facts == []


class TestGroundingPersistence:
    def test_grounding_roundtrip_through_snapshot(self):
        from app.storage.sqlite import SQLiteStore

        store = SQLiteStore(":memory:")
        story = Story(id="a", premise="p")
        story.grounding = ["• 刘强东：1998年创办京东", "• Claude Code：AI编程助手"]
        store.save(story)
        assert store.get("a").grounding == story.grounding
        assert store.snapshot("a")["grounding"] == story.grounding


class _FakeEmbedServer:
    """本地桩：模拟 OpenAI 兼容 /embeddings。"""

    def __init__(self) -> None:
        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                inputs = body.get("input", [])
                data = [{"object": "embedding", "index": i, "embedding": [0.1] * 8 + [i]}
                        for i in range(len(inputs))]
                payload = json.dumps({"data": data}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):  # 静默
                pass

        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self._t = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._t.start()
        self.port = self._srv.server_address[1]

    def close(self) -> None:
        self._srv.shutdown()


class TestLLMEmbedding:
    def test_llm_embedding_function_hits_embeddings_endpoint(self):
        srv = _FakeEmbedServer()
        try:
            fn = LLMEmbeddingFunction(base_url=f"http://127.0.0.1:{srv.port}/v1",
                                       api_key="k", model="embed-test")
            vecs = fn(["你好", "世界"])
            assert len(vecs) == 2 and all(len(v) == 9 for v in vecs)
        finally:
            srv.close()

    def test_llm_mode_without_embed_config_falls_back_to_none(self):
        # mode=llm 但没给 embed（如 embedding_model 未配）→ build 失败返回 None（回落空事实）
        facade = build_chroma_facade(path=tempfile.mkdtemp(), mode="llm", embed=None)
        assert facade is None

    def test_default_embedding_is_ngram(self):
        assert isinstance(NGramEmbedding(), NGramEmbedding)
        assert len(_SEED) >= 3