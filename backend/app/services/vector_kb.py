"""Chroma 向量知识库：内置真实世界事实的唯一来源。

- 事实以 Chroma 集合 `grounding` 持久化，检索=向量查询（cosine）。
- `_SEED` 仅作启动期引导：按稳定 id 幂等插入（只补空缺，不覆盖已有项）。
  此后增删改直接在 Chroma 里操作，Chroma 是唯一权威源；种子不再回写。
- embedding 可插拔：默认 NGramEmbedding（离线、中文可用），
  可选 LLMEmbeddingFunction（走外部 /embeddings，语义更强）。
"""
from __future__ import annotations

import hashlib
import math
import re

import chromadb
from chromadb.utils.embedding_functions import EmbeddingFunction


# 字符级 n-gram 离线向量：确定性、中文可用、零模型下载、CPU 快。
_NGRAM_DIM = 512
_NGRAM_NS = (2, 3)


def _ngram_vec(text: str, dim: int = _NGRAM_DIM, ns=_NGRAM_NS) -> list[float]:
    v = [0.0] * dim
    s = re.sub(r"\s+", "", (text or "").lower())
    for n in ns:
        for i in range(len(s) - n + 1):
            h = hashlib.blake2b(s[i:i + n].encode()).digest()
            idx = int.from_bytes(h[:4], "big") % dim
            v[idx] += 1.0
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


class NGramEmbedding(EmbeddingFunction):
    def __init__(self) -> None:
        self._dim = _NGRAM_DIM

    def name(self) -> str:
        return "ngram-hash"

    def dimension(self) -> int:
        return self._dim

    def get_config(self) -> dict:
        return {"dim": self._dim, "ns": list(_NGRAM_NS)}

    def __call__(self, input) -> list[list[float]]:
        if isinstance(input, str):
            input = [input]
        return [_ngram_vec(t, self._dim) for t in input]


class LLMEmbeddingFunction(EmbeddingFunction):
    """外部 LLM embedding：同步调用 `{base_url}/embeddings`（OpenAI 兼容协议）。

    Chroma 的 add/query 会同步调用 embedding_function，因此用同步 httpx.Client 直连，
    不在异步事件循环里跑，避免与 FastAPI 的 loop 冲突。
    """

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: float = 20.0) -> None:
        self._base_url = base_url.rstrip("/")
        base = self._base_url
        if base.endswith("/chat/completions"):
            base = base[: -len("/chat/completions")]
        elif base.endswith("/completions"):
            base = base[: -len("/completions")]
        self._url = f"{base}/embeddings"
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def name(self) -> str:
        return f"llm-{self._model}"

    def dimension(self) -> int:
        # 多数 OpenAI 兼容 embedding 为 1536；做归一化，维数差异只影响存储不改变余弦阈值用途。
        return 1536

    def get_config(self) -> dict:
        return {"model": self._model}

    def __call__(self, input):
        import httpx
        if isinstance(input, str):
            input = [input]
        payload = {"model": self._model, "input": list(input)}
        with httpx.Client(timeout=self._timeout) as client:
            res = client.post(self._url, json=payload,
                              headers={"Authorization": f"Bearer {self._api_key}",
                                       "Content-Type": "application/json"})
            res.raise_for_status()
            data = res.json()
        return [item["embedding"] for item in data["data"]]


def _bigrams(text: str) -> set[str]:
    s = re.sub(r"\s+", "", (text or "").lower())
    return {s[i:i + 2] for i in range(len(s) - 1)}


# 待注入的内置真实世界事实（真实人物履历 / 知名技术产品定义）。
# 仅启动期引导写库；运行期应以 Chroma 中数据为准，增删改直接改 Chroma 集合。
_SEED = [
    {
        "id": "liuqiangdong", "entity": "刘强东", "category": "person",
        "role": "中国企业家、京东集团创始人",
        "facts": [
            "1998年6月18日在中关村创办京东公司并担任总经理",
            "2004年创办“京东多媒体网”并出任CEO",
            "2013年担任第十二届上海市政协委员",
            "2014年5月带领京东在美国纳斯达克证券交易所上市",
            "2020年6月18日京东集团在中国香港二次上市，股份代码“9618”",
            "曾入选《财富》“全球50位最伟大的领导者”",
        ],
        "note": "刘强东是身家极高的电商巨头创办者，现实中不会被一位普通青年以‘资助落难’之姿救起。若剧情要写他落魄或需要时间跳跃资助，必须明确写成架空改写，不得宣称以史实为据；时间线也不应把他创业的1998—2020年事记到2023—2028年。",
    },
    {
        "id": "claudecode", "entity": "Claude Code", "category": "product",
        "role": "AI 编程助手（Anthropic 产品）",
        "facts": [
            "Claude Code 是 AI 公司 Anthropic 推出的编程助手/智能体，用于协助写代码、运行命令、读写文件等开发工作",
            "在现实当下乃至故事设定的近未来（如2028年）都属常见的生产力工具，并不稀有神秘",
        ],
        "note": "不要把它写成‘内含商业机密的隐秘记事应用’或神秘金手指，那是对该产品的误写。",
    },
    {
        "id": "jd", "entity": "京东", "category": "company",
        "role": "中国电商与物流企业",
        "facts": [
            "京东由刘强东于1998年6月在中关村创立，后来成为中国头部电商与自营物流企业",
            "2014年5月赴美国纳斯达克上市，2020年6月18日在香港二次上市，股份代码“9618”",
        ],
        "note": "京东是成立20余年的成熟企业，剧情时间线不要把它的创始年份前移到近未来。",
    },
]

# 内置知识库声明的真实实体名。仅这些名字算"真实实体"；判断事实/历史线是否混入真实内容时以它为准。
KNOWN_ENTITIES: list[str] = [ent["entity"] for ent in _SEED]


class ChromaKBFacade:
    """Chroma 持久化向量知识库检索门面。"""

    def __init__(self, *, path: str, embedding_function: EmbeddingFunction,
                 seed: list[dict] | None = None) -> None:
        self._client = chromadb.PersistentClient(path=path)
        self._col = self._client.get_or_create_collection(
            name="grounding", embedding_function=embedding_function,
            metadata={"hnsw:space": "cosine"},
        )
        self._seed(seed or _SEED)

    # ---- 种子（幂等：只补不覆盖）----
    def _seed(self, entities: list[dict]) -> None:
        existing = set(self._col.get(include=[])["ids"])
        ids, docs, metas = [], [], []
        for ent in entities:
            eid, entity, category = ent["id"], ent["entity"], ent.get("category", "")
            role = (ent.get("role") or "").strip()
            if role:
                rid = f"{eid}-role"
                if rid not in existing:
                    ids.append(rid)
                    docs.append(f"{entity}：{role}")
                    metas.append({"entity": entity, "category": category, "kind": "role"})
            for i, f in enumerate(ent.get("facts", [])):
                fid = f"{eid}-f{i}"
                if fid not in existing:
                    ids.append(fid)
                    docs.append(f"{entity}：{f}")
                    metas.append({"entity": entity, "category": category, "kind": "fact"})
            note = (ent.get("note") or "").strip()
            if note:
                nid = f"{eid}-note"
                if nid not in existing:
                    ids.append(nid)
                    docs.append(f"{entity}：{note}")
                    metas.append({"entity": entity, "category": category, "kind": "note"})
        if ids:
            self._col.add(ids=ids, documents=docs, metadatas=metas)

    # ---- 检索 ----
    @staticmethod
    def _keep(query: str, doc: str, sim: float) -> bool:
        """双重门：词重合度（离线 n-gram 的主要判据）或余弦相似度（LLM embedding 的主判据）。"""
        if _bigrams(query) & _bigrams(doc):
            return True
        return sim >= 0.5

    def query(self, text: str, top_k: int = 8) -> list[dict]:
        if not (text or "").strip():
            return []
        if self._col.count() == 0:
            return []
        # 1) 向量召回 top-k，按"词重合/余弦"双重门挑出命中的实体
        res = self._col.query(query_texts=[text], n_results=top_k)
        entities: list[str] = []
        for doc, dist, meta in zip(res["documents"][0], res["distances"][0], res["metadatas"][0]):
            ent = (meta or {}).get("entity") or ""
            if ent and self._keep(text, doc, 1.0 - dist) and ent not in entities:
                entities.append(ent)
        if not entities:
            return []
        # 2) 整组拉回命中实体的全部事实（补全履历，不依赖 top-k 截断）
        got = self._col.get(include=["documents", "metadatas"])
        out: list[dict] = []
        for doc, meta in zip(got["documents"], got["metadatas"]):
            ent = (meta or {}).get("entity") or ""
            if ent in entities:
                out.append({"entity": ent, "fact": doc})
        out.sort(key=lambda x: entities.index(x["entity"]))
        seen = set()
        dedup = []
        for item in out:
            key = (item["entity"], item["fact"])
            if key not in seen:
                seen.add(key)
                dedup.append(item)
        return dedup


def build_chroma_facade(*, path: str, mode: str = "n-gram",
                        embed: dict | None = None) -> ChromaKBFacade | None:
    """按 config 组装 facade；chromadb 不可用或 llm embedding 未配好 → 返回 None（回落空事实）。"""
    try:
        ef: EmbeddingFunction = NGramEmbedding() if mode not in ("llm",) else LLMEmbeddingFunction(
            base_url=embed["base_url"], api_key=embed["api_key"], model=embed["model"],
        )
        return ChromaKBFacade(path=path, embedding_function=ef)
    except Exception:
        return None