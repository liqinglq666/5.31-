"""
app/infrastructure/vectorstore/milvus.py
-----------------------------------------
拓扑记忆层管理器（TopoMemoryManager）。

职责：
1. 将 Docling 输出的高保真 Markdown 按语义标题层级切分为知识树块。
2. 使用本地轻量 Embedding 模型（MiniLM-L6-v2）生成 384 维稠密向量。
3. 写入 Milvus 向量数据库，构建支持快速语义检索的拓扑记忆层。

设计要点：
- 禁止按固定字数切分，必须以 Markdown 的 # / ## 标题作为语义边界。
- 所有 Milvus 同步 I/O 与 Embedding 编码均包装到 asyncio.to_thread，
  避免阻塞 FastAPI 事件循环。
- Collection 采用自管理策略：首次连接时若不存在则自动创建，
  后续复用已存在的 Schema 与索引。
"""

import asyncio
import logging
import re
import uuid
from typing import List, Dict, Any, Optional

from app.core.config import settings
from app.infrastructure.llm.client import chat_completion

# 语义检索相似度阈值：COSINE distance 低于此值视为噪声，直接丢弃
SIMILARITY_THRESHOLD = 0.3

logger = logging.getLogger(__name__)


class TopoMemoryManager:
    """
    拓扑记忆管理器。

    用法示例：
        manager = TopoMemoryManager()
        await manager.ingest_document(
            doc_id="contract_2024_001",
            md_text="# 合同总则\n..."
        )
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedding_model_name: Optional[str] = None,
        dim: Optional[int] = None,
    ) -> None:
        """
        初始化 Milvus 连接与 Embedding 模型。

        参数均可通过 settings 默认读取，也支持显式传入以方便测试。
        """
        self._host = host or settings.milvus_host
        self._port = port or settings.milvus_port
        self._collection_name = collection_name or settings.milvus_collection
        self._embedding_model_name = embedding_model_name or settings.embedding_model
        self._dim = dim or settings.embedding_dim

        # 懒加载实例
        self._client: Optional[Any] = None
        self._embedding_model: Optional[Any] = None

    # ------------------------------------------------------------------
    # Lazy Initializers
    # ------------------------------------------------------------------
    def _get_milvus_client(self) -> Any:
        """懒加载 MilvusClient（线程安全，底层使用连接池）。"""
        if self._client is None:
            try:
                from pymilvus import MilvusClient
            except ImportError as exc:
                raise ImportError(
                    "pymilvus 未安装，请执行 `pip install pymilvus`"
                ) from exc

            self._client = MilvusClient(
                uri=f"http://{self._host}:{self._port}"
            )
            logger.info(
                f"MilvusClient 已连接: {self._host}:{self._port}"
            )
        return self._client

    # ------------------------------------------------------------------
    # Embedding Model Loader with multi-mirror fallback
    # ------------------------------------------------------------------
    _HF_MIRRORS = [
        "https://hf-mirror.com",
        "https://huggingface.co",
    ]

    @staticmethod
    def _clean_broken_cache(model_name: str) -> None:
        """删除可能因网络中断导致损坏的模型缓存目录。"""
        import os
        import shutil

        cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
        safe_name = model_name.replace("/", "--")
        model_cache = os.path.join(cache_dir, f"models--{safe_name}")
        if os.path.isdir(model_cache):
            logger.warning("[Embedding] 清理损坏的模型缓存: %s", model_cache)
            shutil.rmtree(model_cache, ignore_errors=True)

    def _download_model_with_fallback(self, model_name: str) -> str:
        """多镜像 fallback 下载模型，返回本地缓存路径。

        策略：
        1. 优先尝试 local_files_only=True，如果本地缓存完整则直接复用（零网络）。
        2. 本地没有或缓存损坏时，依次尝试多个镜像下载。
        3. 若本地缓存损坏（如 config.json 缺失 model_type），先清理再重试。
        """
        import os
        from huggingface_hub import snapshot_download
        from huggingface_hub.errors import HFValidationError, HfHubHTTPError

        # 策略 1：本地优先，避免任何网络请求
        try:
            local_path = snapshot_download(repo_id=model_name, local_files_only=True)
            logger.info("[Embedding] 从本地缓存加载模型: %s -> %s", model_name, local_path)
            return local_path
        except Exception:
            logger.info("[Embedding] 本地缓存未命中，尝试网络下载: %s", model_name)

        last_exc: Exception = RuntimeError("No mirror attempted")
        original_endpoint = os.environ.get("HF_ENDPOINT", "")

        for idx, endpoint in enumerate(self._HF_MIRRORS):
            os.environ["HF_ENDPOINT"] = endpoint
            try:
                logger.info(
                    "[Embedding] 尝试从镜像 %d/%d 下载模型: %s (endpoint=%s)",
                    idx + 1,
                    len(self._HF_MIRRORS),
                    model_name,
                    endpoint,
                )
                local_path = snapshot_download(
                    repo_id=model_name,
                    local_files_only=False,
                )
                logger.info(
                    "[Embedding] 模型下载成功: %s -> %s", model_name, local_path
                )
                return local_path
            except (HFValidationError, HfHubHTTPError, Exception) as exc:
                logger.warning(
                    "[Embedding] 镜像 %s 下载失败: %s", endpoint, exc
                )
                last_exc = exc
                continue
            finally:
                # 恢复原始 endpoint，避免影响其他库
                if original_endpoint:
                    os.environ["HF_ENDPOINT"] = original_endpoint
                else:
                    os.environ.pop("HF_ENDPOINT", None)

        raise RuntimeError(
            f"所有镜像均无法下载模型 {model_name}，最后一个错误: {last_exc}"
        ) from last_exc

    def _get_embedding_model(self) -> Any:
        """懒加载 sentence-transformers Embedding 模型（本地优先 + 多镜像 fallback）。"""
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ImportError(
                    "sentence-transformers 未安装，请执行 "
                    "`pip install sentence-transformers`"
                ) from exc

            # 策略 1：优先使用用户配置的本地绝对路径（绕过任何网络下载）
            local_path: str | None = None
            if settings.embedding_model_local_path:
                import os as _os
                if _os.path.isdir(settings.embedding_model_local_path):
                    local_path = settings.embedding_model_local_path
                    logger.info(
                        "[Embedding] 使用本地模型路径: %s", local_path
                    )
                else:
                    logger.warning(
                        "[Embedding] 配置的本地模型路径不存在: %s，回退到在线下载",
                        settings.embedding_model_local_path,
                    )

            # 策略 2：本地未配置或路径不存在，走多镜像下载
            if local_path is None:
                local_path = self._download_model_with_fallback(self._embedding_model_name)

            # 从本地路径加载
            try:
                self._embedding_model = SentenceTransformer(local_path)
            except ValueError as exc:
                if "model_type" in str(exc) or "Unrecognized model" in str(exc):
                    logger.warning(
                        "[Embedding] 本地缓存损坏 (%s)，清理后重新下载...",
                        exc,
                    )
                    self._clean_broken_cache(self._embedding_model_name)
                    local_path = self._download_model_with_fallback(
                        self._embedding_model_name
                    )
                    self._embedding_model = SentenceTransformer(local_path)
                else:
                    raise

            logger.info(
                "Embedding 模型加载完成: %s (本地路径: %s, 输出维度 %d)",
                self._embedding_model_name,
                local_path,
                self._dim,
            )
        return self._embedding_model

    # ------------------------------------------------------------------
    # Collection Management
    # ------------------------------------------------------------------
    def _ensure_collection(self) -> None:
        """
        确保目标 Collection 存在。
        若不存在，自动创建 Schema + IVF_FLAT 索引；若已存在则跳过。
        此方法是同步的，应在 asyncio.to_thread 中调用。
        """
        client = self._get_milvus_client()

        # 检查 Collection 是否已存在
        if client.has_collection(collection_name=self._collection_name):
            logger.debug(f"Collection '{self._collection_name}' 已存在，跳过创建")
            return

        # 创建 Schema
        from pymilvus import DataType

        schema = client.create_schema(
            auto_id=False,
            enable_dynamic_field=False,
        )
        schema.add_field("chunk_id", DataType.VARCHAR, max_length=64, is_primary=True)
        schema.add_field("doc_id", DataType.VARCHAR, max_length=128)
        schema.add_field("text", DataType.VARCHAR, max_length=8192)
        schema.add_field("level_1", DataType.VARCHAR, max_length=256)
        schema.add_field("level_2", DataType.VARCHAR, max_length=256)
        schema.add_field("is_summary", DataType.BOOL)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=self._dim)

        # 创建 Collection
        client.create_collection(
            collection_name=self._collection_name,
            schema=schema,
        )

        # 为向量字段创建 IVF_FLAT 索引
        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="IVF_FLAT",
            metric_type="COSINE",
            params={"nlist": 128},
        )
        client.create_index(
            collection_name=self._collection_name,
            index_params=index_params,
        )

        logger.info(
            f"Collection '{self._collection_name}' 创建完成，"
            f"Schema 字段: chunk_id, doc_id, text, level_1, level_2, "
            f"is_summary, embedding(dim={self._dim})"
        )

    # ------------------------------------------------------------------
    # Markdown Chunking
    # ------------------------------------------------------------------
    @staticmethod
    def _chunk_markdown(md_text: str) -> List[Dict[str, Any]]:
        """
        按 Markdown 标题层级（# / ##）进行语义切块。

        核心规则：
        1. 禁止按固定字数切分，必须以 # / ## 作为边界。
        2. 一级标题 (#) 与二级标题 (##) 之间的内容构成一个语义块。
        3. 提取每个块的 level_1（所属一级标题）和 level_2（所属二级标题）作为拓扑标签。
        4. 若某块长度超过 2000 字符，以段落（空行）为二级边界进行再切分，
           确保单个 chunk 的文本长度可控。

        返回：
            字典列表，每个字典包含：
            - text: 块文本内容
            - level_1: 所属一级标题（若无则为空字符串）
            - level_2: 所属二级标题（若无则为空字符串）
            - is_summary: 是否为标题摘要块（仅含标题本身）
        """
        if not md_text or not md_text.strip():
            return []

        chunks: List[Dict[str, Any]] = []

        # 按一级标题 (# ) 分割全文，保留分隔符
        # 正则说明：匹配行首的 `# ` 或 `## `，但要先把一级标题和二级标题区分开
        # 策略：先按一级标题切分，再在每一段内部按二级标题切分
        sections = re.split(r'(?m)^(?=# )', md_text)

        for section in sections:
            section = section.strip()
            if not section:
                continue

            # 提取一级标题
            level_1 = ""
            first_line = section.split('\n', 1)[0]
            m1 = re.match(r'^# (.+)$', first_line.strip())
            if m1:
                level_1 = m1.group(1).strip()

            # 去掉一级标题行本身，对剩余内容按二级标题 (## ) 切分
            body = section[len(first_line):].lstrip('\n')
            if not body.strip():
                # 仅有一级标题，生成一个摘要块
                chunks.append({
                    "text": first_line.strip(),
                    "level_1": level_1,
                    "level_2": "",
                    "is_summary": True,
                })
                continue

            sub_sections = re.split(r'(?m)^(?=## )', body)

            for sub in sub_sections:
                sub = sub.strip()
                if not sub:
                    continue

                # 提取二级标题
                level_2 = ""
                sub_first = sub.split('\n', 1)[0]
                m2 = re.match(r'^## (.+)$', sub_first.strip())
                if m2:
                    level_2 = m2.group(1).strip()

                # 若某二级标题下的内容过长，按段落再切分
                content = sub
                if len(content) > 2000:
                    paragraphs = content.split('\n\n')
                    current_text = ""
                    for para in paragraphs:
                        if len(current_text) + len(para) + 2 > 2000:
                            if current_text.strip():
                                chunks.append({
                                    "text": current_text.strip(),
                                    "level_1": level_1,
                                    "level_2": level_2,
                                    "is_summary": False,
                                })
                            current_text = para
                        else:
                            current_text += '\n\n' + para if current_text else para
                    if current_text.strip():
                        chunks.append({
                            "text": current_text.strip(),
                            "level_1": level_1,
                            "level_2": level_2,
                            "is_summary": False,
                        })
                else:
                    chunks.append({
                        "text": content,
                        "level_1": level_1,
                        "level_2": level_2,
                        "is_summary": False,
                    })

        # 后处理：过滤掉纯空块
        chunks = [c for c in chunks if c["text"].strip()]

        logger.info(f"Markdown 切块完成：共 {len(chunks)} 个语义块")
        return chunks

    # ------------------------------------------------------------------
    # Embedding Generation
    # ------------------------------------------------------------------
    def _encode_texts(self, texts: List[str]) -> List[List[float]]:
        """
        将文本列表编码为稠密向量。
        同步方法，需在 asyncio.to_thread 中调用。
        """
        model = self._get_embedding_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        # 转换为 Python 原生 list，方便 pymilvus 序列化
        return [emb.tolist() for emb in embeddings]

    # ------------------------------------------------------------------
    # Async Public API
    # ------------------------------------------------------------------
    async def ingest_document(self, doc_id: str, md_text: str) -> Dict[str, Any]:
        """
        将一份 Markdown 文档切块、向量化，并写入 Milvus。

        参数：
            doc_id: 文档唯一标识（如合同编号）。
            md_text: Docling 解析输出的高保真 Markdown 全文。

        返回：
            {"inserted": int, "doc_id": str}
        """
        if not doc_id or not doc_id.strip():
            raise ValueError("doc_id 不能为空")
        if not md_text or not md_text.strip():
            raise ValueError("md_text 不能为空")

        # 预加载 embedding 模型（避免在线程中首次加载触发死锁）
        _ = self._get_embedding_model()

        # 1. 语义切块
        chunks = self._chunk_markdown(md_text)
        if not chunks:
            logger.warning(f"doc_id={doc_id} 切块后为空，跳过入库")
            return {"inserted": 0, "doc_id": doc_id}

        # 2. 确保 Collection 存在（同步操作包装到线程）
        logger.info("[ingest] ensuring collection...")
        await asyncio.to_thread(self._ensure_collection)
        logger.info("[ingest] collection ensured")

        # 3. 批量生成 Embedding（同步操作包装到线程）
        texts = [c["text"] for c in chunks]
        logger.info("[ingest] encoding %d chunks...", len(texts))
        embeddings = await asyncio.to_thread(self._encode_texts, texts)
        logger.info("[ingest] encoded %d embeddings", len(embeddings))

        # 4. 组装 Milvus 数据行
        rows: List[Dict[str, Any]] = []
        for chunk, emb in zip(chunks, embeddings):
            rows.append({
                "chunk_id": str(uuid.uuid4()).replace("-", ""),
                "doc_id": doc_id,
                "text": chunk["text"][:8192],  # 受限于 VARCHAR max_length
                "level_1": chunk["level_1"][:256],
                "level_2": chunk["level_2"][:256],
                "is_summary": chunk["is_summary"],
                "embedding": emb,
            })

        # 5. 写入 Milvus（同步操作包装到线程）
        logger.info("[ingest] inserting %d rows...", len(rows))

        def _insert() -> None:
            client = self._get_milvus_client()
            client.insert(
                collection_name=self._collection_name,
                data=rows,
            )
            # 强制 flush，确保刚写入的数据立即可被 query/search 命中
            # 开发环境中 Milvus flush 可能因 segment 积压而无限阻塞，
            # 使用 wait_for 防止挂死整个比对任务（数据仍在 growing segments 中可搜索）
            client.flush(collection_name=self._collection_name)

        try:
            await asyncio.wait_for(asyncio.to_thread(_insert), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning(
                "[ingest] Milvus flush 超时（15s），数据已写入 growing segments，"
                "后续 search_similar 通过 load_collection() 仍可命中。"
                "doc_id=%s, chunks=%d",
                doc_id,
                len(rows),
            )
        logger.info("[ingest] insert done")
        logger.info(
            f"文档入库成功: doc_id={doc_id}, "
            f"chunks={len(rows)}"
        )

        return {"inserted": len(rows), "doc_id": doc_id}

    async def search_similar(
        self,
        query_text: str,
        top_k: int = 5,
        doc_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        基于向量相似度检索最相关的语义块。

        参数：
            query_text: 查询文本（如 LLM 提取的某一条款）。
            top_k: 返回的最相似块数量。
            doc_id: 若指定，则仅在同一文档内检索；否则跨文档全局检索。

        返回：
            命中块列表，每个字典包含 chunk_id, doc_id, text, level_1,
            level_2, distance（余弦距离）。
        """
        if not query_text or not query_text.strip():
            return []

        # 1. 生成查询向量
        query_emb = await asyncio.to_thread(
            self._encode_texts, [query_text.strip()]
        )
        if not query_emb:
            return []

        # 2. 执行向量检索
        def _search() -> List[Dict[str, Any]]:
            client = self._get_milvus_client()

            # 确保 Collection 已加载到内存（Milvus 2.x 必须显式 load）
            client.load_collection(collection_name=self._collection_name)

            filter_expr = f'doc_id == "{doc_id}"' if doc_id else ""

            results = client.search(
                collection_name=self._collection_name,
                data=query_emb,
                filter=filter_expr,
                limit=top_k,
                output_fields=[
                    "chunk_id",
                    "doc_id",
                    "text",
                    "level_1",
                    "level_2",
                    "is_summary",
                ],
                search_params={"metric_type": "COSINE", "params": {"nprobe": 10}},
            )

            hits: List[Dict[str, Any]] = []
            for result_group in results:
                for hit in result_group:
                    distance = hit.get("distance", 0.0)
                    # 过滤低质量噪声：COSINE distance 低于阈值直接丢弃
                    if distance < SIMILARITY_THRESHOLD:
                        continue
                    hits.append({
                        "chunk_id": hit.get("entity", {}).get("chunk_id", ""),
                        "doc_id": hit.get("entity", {}).get("doc_id", ""),
                        "text": hit.get("entity", {}).get("text", ""),
                        "level_1": hit.get("entity", {}).get("level_1", ""),
                        "level_2": hit.get("entity", {}).get("level_2", ""),
                        "is_summary": hit.get("entity", {}).get("is_summary", False),
                        "distance": distance,
                    })
            return hits

        hits = await asyncio.to_thread(_search)
        logger.info(
            f"语义检索完成: query='{query_text[:30]}...', "
            f"hits={len(hits)}, doc_filter={doc_id or 'None'}"
        )
        return hits

    async def delete_by_doc_id(self, doc_id: str) -> int:
        """
        按 doc_id 删除该文档下的所有语义块（含底层切片与 RAPTOR 摘要）。

        使用 MilvusClient 执行 filter 删除，并带 timeout 的 flush 确保
        标记删除落盘。flush 超时时数据已在 growing segments 中标记删除，
        不影响后续查询。

        Returns:
            实际删除的行数。
        """
        if not doc_id:
            return 0

        def _delete() -> int:
            client = self._get_milvus_client()
            try:
                # MilvusClient.delete 支持 filter 表达式删除
                res = client.delete(
                    collection_name=self._collection_name,
                    filter=f'doc_id == "{doc_id}"',
                )
                delete_count = res.get("deleted_count", 0) if isinstance(res, dict) else 0
                logger.info(
                    "删除文档语义块: doc_id=%s, deleted=%d", doc_id, delete_count
                )
                return delete_count
            except Exception as exc:
                logger.error(
                    "删除文档语义块失败: doc_id=%s, error=%s",
                    doc_id,
                    exc,
                    exc_info=True,
                )
                return 0

        def _flush() -> None:
            client = self._get_milvus_client()
            try:
                client.flush(collection_name=self._collection_name)
            except Exception as exc:
                logger.warning(
                    "[delete_by_doc_id] flush 失败（非阻断）: doc_id=%s, %s",
                    doc_id, exc,
                )

        delete_count = await asyncio.to_thread(_delete)

        # flush 单独加 timeout，避免 channel 异常导致无限阻塞
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_flush), timeout=15.0
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[delete_by_doc_id] flush 超时（15s），数据已标记删除，"
                "doc_id=%s", doc_id,
            )

        return delete_count

    # ------------------------------------------------------------------
    # RAPTOR 树状摘要生成（带 CoVe 防幻觉机制）
    # ------------------------------------------------------------------
    async def _generate_raptor_summary(
        self,
        chunks_text: str,
        level_1_title: str,
        model_id: Optional[str] = None,
    ) -> str:
        """
        为同一章节的底层切片生成宏观摘要。

        强制嵌入 CoVe（Chain-of-Verification）防幻觉 Prompt，要求 LLM：
        1. 在生成摘要后自我审计，删除无法在原文字面中找到出处的具体事实。
        2. 保留原文中的交叉引用指针（如“参见附件”、“按第X条执行”）。
        """
        system_prompt = (
            "你是一位严谨的法律合同审查专家。你的任务是对合同条款切片生成宏观摘要，"
            "同时严格遵守以下防幻觉规则。"
        )

        user_prompt = (
            f"【所属章节】\n{level_1_title}\n\n"
            f"【合同条款切片原文】\n{chunks_text}\n\n"
            f"任务：请对以上合同条款切片生成宏观摘要。\n\n"
            f"【防幻觉核实 (CoVe)】：在生成摘要后，你必须执行严格的自我审计："
            f"摘要中出现的任何具体金额、天数、违约比例、机构名称，是否在原文中能找到一模一样的出处？"
            f"若无，立即删除该虚构事实。\n\n"
            f"【引用保留】：若原文存在'参见附件'、'按第X条执行'等交叉引用，"
            f"必须在摘要中醒目保留该引用指针。\n\n"
            f"请直接输出摘要内容，不要包含额外解释。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            summary, usage = await chat_completion(
                messages=messages,
                model_id=model_id,
                temperature=-1.0,
            )
            logger.info(
                "[RAPTOR] 摘要生成完成: level_1='%s', tokens=%s",
                level_1_title,
                usage.get("total_tokens", 0),
            )
            return summary.strip()
        except Exception as exc:
            logger.warning(
                "[RAPTOR] 摘要生成失败: level_1='%s', error=%s",
                level_1_title,
                exc,
            )
            # 降级：直接返回原文前 512 字符作为兜底摘要
            fallback = chunks_text[:512].strip()
            return fallback + "\n\n（摘要生成失败，此处为原文节选）"

    async def build_raptor_tree(
        self,
        doc_id: str,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        构建 RAPTOR 摘要树。

        流程：
        1. 从 Milvus 查询该 doc_id 下所有 is_summary == False 的叶子节点。
        2. 按 level_1（一级标题/章节）将节点内容聚合拼接。
        3. 并发调用 _generate_raptor_summary 生成各章节的宏观摘要。
        4. 将生成的摘要作为新的父节点存回 Milvus，标记 is_summary=True。

        返回：
            {"inserted": int, "doc_id": str, "summaries": List[str]}
        """
        if not doc_id or not doc_id.strip():
            raise ValueError("doc_id 不能为空")

        # ---------- 1. 查询叶子节点 ----------
        def _query_leaves() -> List[Dict[str, Any]]:
            client = self._get_milvus_client()
            client.load_collection(collection_name=self._collection_name)
            results = client.query(
                collection_name=self._collection_name,
                filter=f'doc_id == "{doc_id}" and is_summary == False',
                output_fields=["chunk_id", "text", "level_1", "level_2", "is_summary"],
                limit=10000,
            )
            return results

        leaves = await asyncio.to_thread(_query_leaves)
        if not leaves:
            logger.info(f"[RAPTOR] doc_id={doc_id} 无叶子节点，跳过树构建")
            return {"inserted": 0, "doc_id": doc_id, "summaries": []}

        # ---------- 2. 按 level_1 聚合 ----------
        groups: Dict[str, List[str]] = {}
        for leaf in leaves:
            l1 = leaf.get("level_1") or "未分类"
            text = leaf.get("text", "")
            if text:
                groups.setdefault(l1, []).append(text)

        if not groups:
            logger.info(f"[RAPTOR] doc_id={doc_id} 聚合后无有效内容，跳过")
            return {"inserted": 0, "doc_id": doc_id, "summaries": []}

        # ---------- 3. 并发生成摘要 ----------
        summary_tasks = []
        for level_1, texts in groups.items():
            combined = f"\n\n{'-'*20}\n\n".join(texts)
            summary_tasks.append(
                self._generate_raptor_summary(
                    chunks_text=combined,
                    level_1_title=level_1,
                    model_id=model_id,
                )
            )

        summaries = await asyncio.gather(*summary_tasks, return_exceptions=True)

        # ---------- 4. 组装父节点并入库 ----------
        rows: List[Dict[str, Any]] = []
        summary_texts: List[str] = []
        for (level_1, texts), summary in zip(groups.items(), summaries):
            if isinstance(summary, Exception):
                logger.warning(
                    "[RAPTOR] 摘要生成异常，跳过入库: level_1='%s', error=%s",
                    level_1,
                    summary,
                )
                continue
            summary_texts.append(summary)
            rows.append({
                "chunk_id": str(uuid.uuid4()).replace("-", ""),
                "doc_id": doc_id,
                "text": summary[:8192],
                "level_1": level_1[:256],
                "level_2": "",  # 摘要节点无二级标题
                "is_summary": True,
                "embedding": None,  # 稍后批量编码
            })

        if not rows:
            return {"inserted": 0, "doc_id": doc_id, "summaries": []}

        # 批量生成 Embedding
        summary_texts_for_emb = [r["text"] for r in rows]
        embeddings = await asyncio.to_thread(self._encode_texts, summary_texts_for_emb)

        for row, emb in zip(rows, embeddings):
            row["embedding"] = emb

        # 写入 Milvus
        def _insert_summaries() -> None:
            client = self._get_milvus_client()
            client.insert(
                collection_name=self._collection_name,
                data=rows,
            )
            client.flush(collection_name=self._collection_name)

        try:
            await asyncio.wait_for(
                asyncio.to_thread(_insert_summaries), timeout=15.0
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[RAPTOR] Milvus flush 超时（15s），摘要数据已写入 growing segments，"
                "doc_id=%s, summaries=%d",
                doc_id,
                len(rows),
            )
        logger.info(
            f"[RAPTOR] 摘要树入库完成: doc_id={doc_id}, "
            f"summaries={len(rows)}, chapters={list(groups.keys())}"
        )

        return {
            "inserted": len(rows),
            "doc_id": doc_id,
            "summaries": summary_texts,
        }

    # ------------------------------------------------------------------
    # 轻量级 GraphRAG & 双锚定全息上下文检索
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_references(text: str) -> List[str]:
        """
        从文本中提取法律/合同引用标记（如“第X条”、“附件X”）。

        返回去重后的引用目标列表，用于图谱横向追踪。
        """
        if not text:
            return []

        refs: List[str] = []

        # 匹配“第X条”类引用（支持中文数字、阿拉伯数字、小数点、空格）
        # 示例：第七条、第7条、第 7.4 条、第10.2条
        pattern_article = re.compile(
            r'第\s*[一二三四五六七八九十百零\d]+(?:\.\d+)?\s*条'
        )
        refs.extend(pattern_article.findall(text))

        # 匹配“附件X”类引用（支持中文数字、阿拉伯数字、英文字母）
        # 示例：附件一、附件1、附件A、附件 3
        pattern_appendix = re.compile(
            r'附件\s*[一二三四五六七八九十\dA-Za-z]+'
        )
        refs.extend(pattern_appendix.findall(text))

        # 清洗：去除多余空格，统一半角
        cleaned = []
        for r in refs:
            r = re.sub(r'\s+', '', r)  # 去掉所有空格
            cleaned.append(r)

        # 去重并保持顺序
        seen = set()
        unique_refs = []
        for r in cleaned:
            if r not in seen:
                seen.add(r)
                unique_refs.append(r)

        return unique_refs

    async def retrieve_context(
        self,
        doc_id: str,
        query: str,
        top_k: int = 2,
    ) -> str:
        """
        全息上下文检索：向量召回 → 双锚定补全 → 图谱横向追踪 → 结构化组装。

        返回一段层次分明、带标题标注的上下文字符串，供上层 Agent 直接消费。
        """
        if not doc_id or not query:
            return ""

        # ==================== 阶段 A：向量召回 ====================
        hits = await self.search_similar(
            query_text=query,
            top_k=top_k,
            doc_id=doc_id,
        )
        if not hits:
            return ""

        # 用于去重的 chunk_id 集合
        collected_ids: set = {h["chunk_id"] for h in hits}
        context_pieces: List[Dict[str, Any]] = []

        # ==================== 阶段 B：双锚定补全 ====================
        def _dual_anchor_fetch(
            anchor_hits: List[Dict[str, Any]]
        ) -> List[Dict[str, Any]]:
            """同步函数：在 Milvus 中根据摘要/叶子关系互为补全。"""
            client = self._get_milvus_client()
            client.load_collection(collection_name=self._collection_name)
            extra_rows: List[Dict[str, Any]] = []

            for hit in anchor_hits:
                level_1 = hit.get("level_1", "")
                is_summary = hit.get("is_summary", False)
                if not level_1:
                    continue

                if is_summary:
                    # 摘要节点 → 拉取同章节的核心叶子节点（最多 2 个）
                    filter_expr = (
                        f'doc_id == "{doc_id}" and is_summary == False '
                        f'and level_1 == "{level_1}"'
                    )
                    leaf_results = client.query(
                        collection_name=self._collection_name,
                        filter=filter_expr,
                        output_fields=["chunk_id", "text", "level_1", "level_2", "is_summary"],
                        limit=2,
                    )
                    for lr in leaf_results:
                        cid = lr.get("chunk_id")
                        if cid and cid not in collected_ids:
                            collected_ids.add(cid)
                            extra_rows.append({
                                "chunk_id": cid,
                                "text": lr.get("text", ""),
                                "level_1": lr.get("level_1", ""),
                                "level_2": lr.get("level_2", ""),
                                "is_summary": False,
                                "source": "dual_anchor_leaf",
                            })
                else:
                    # 叶子节点 → 拉取同章节的父级摘要（最多 1 个）
                    filter_expr = (
                        f'doc_id == "{doc_id}" and is_summary == True '
                        f'and level_1 == "{level_1}"'
                    )
                    summary_results = client.query(
                        collection_name=self._collection_name,
                        filter=filter_expr,
                        output_fields=["chunk_id", "text", "level_1", "level_2", "is_summary"],
                        limit=1,
                    )
                    for sr in summary_results:
                        cid = sr.get("chunk_id")
                        if cid and cid not in collected_ids:
                            collected_ids.add(cid)
                            extra_rows.append({
                                "chunk_id": cid,
                                "text": sr.get("text", ""),
                                "level_1": sr.get("level_1", ""),
                                "level_2": sr.get("level_2", ""),
                                "is_summary": True,
                                "source": "dual_anchor_summary",
                            })
            return extra_rows

        extra_from_dual = await asyncio.to_thread(_dual_anchor_fetch, hits)

        # 组装初始上下文片段
        for h in hits:
            context_pieces.append({
                "chunk_id": h["chunk_id"],
                "text": h.get("text", ""),
                "level_1": h.get("level_1", ""),
                "level_2": h.get("level_2", ""),
                "is_summary": h.get("is_summary", False),
                "source": "vector_search",
            })
        context_pieces.extend(extra_from_dual)

        # ==================== 阶段 C：图谱横向追踪 ====================
        # 1. 从所有已收集文本中提取引用标记
        all_text = "\n".join([p["text"] for p in context_pieces])
        refs = self._extract_references(all_text)

        def _graph_trace(ref_targets: List[str]) -> List[Dict[str, Any]]:
            """同步函数：根据引用标记在 Milvus 中横向检索被引用的条款。"""
            client = self._get_milvus_client()
            client.load_collection(collection_name=self._collection_name)
            trace_rows: List[Dict[str, Any]] = []

            for ref in ref_targets:
                # 策略：先用完整引用做模糊匹配，再提取核心编号做兜底匹配
                # Milvus like 语法：使用 % 作为通配符
                escaped_ref = ref.replace('"', '\\"')
                # 提取核心数字/标识符用于兜底（如 "第7.4条" → "7.4"）
                core_id_match = re.search(r'[\d.]+|[一二三四五六七八九十百]+', ref)
                core_id = core_id_match.group(0) if core_id_match else escaped_ref

                like_conditions = [
                    f'level_2 like "%{escaped_ref}%"',
                    f'text like "%{escaped_ref}%"',
                ]
                if core_id != escaped_ref:
                    like_conditions.extend([
                        f'level_2 like "%{core_id}%"',
                        f'text like "%{core_id}%"',
                    ])

                filter_expr = (
                    f'doc_id == "{doc_id}" and is_summary == False and '
                    f'({" or ".join(like_conditions)})'
                )
                try:
                    ref_results = client.query(
                        collection_name=self._collection_name,
                        filter=filter_expr,
                        output_fields=["chunk_id", "text", "level_1", "level_2", "is_summary"],
                        limit=2,
                    )
                    for rr in ref_results:
                        cid = rr.get("chunk_id")
                        if cid and cid not in collected_ids:
                            collected_ids.add(cid)
                            trace_rows.append({
                                "chunk_id": cid,
                                "text": rr.get("text", ""),
                                "level_1": rr.get("level_1", ""),
                                "level_2": rr.get("level_2", ""),
                                "is_summary": False,
                                "source": f"graph_ref:{ref}",
                            })
                except Exception as exc:
                    logger.debug(
                        "[GraphRAG] 引用追踪查询失败: ref=%s, error=%s",
                        ref,
                        exc,
                    )
            return trace_rows

        extra_from_graph = []
        if refs:
            extra_from_graph = await asyncio.to_thread(_graph_trace, refs)
            context_pieces.extend(extra_from_graph)

        logger.info(
            "[GraphRAG] 检索闭环完成: doc_id=%s, vector=%s, dual=%s, graph=%s, refs=%s",
            doc_id,
            len(hits),
            len(extra_from_dual),
            len(extra_from_graph),
            refs,
        )

        # ==================== 阶段 D：结构化组装 ====================
        # 按 level_1 分组，先放摘要，后放叶子，最后放引用补充
        groups: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for piece in context_pieces:
            l1 = piece.get("level_1") or "未分类"
            if l1 not in groups:
                groups[l1] = {"summaries": [], "leaves": [], "refs": []}

            src = piece.get("source", "")
            if src.startswith("graph_ref"):
                groups[l1]["refs"].append(piece)
            elif piece.get("is_summary"):
                groups[l1]["summaries"].append(piece)
            else:
                groups[l1]["leaves"].append(piece)

        lines: List[str] = []
        lines.append("=" * 40)
        lines.append("【全息上下文检索结果】")
        lines.append("=" * 40)

        for idx, (l1, bucket) in enumerate(groups.items(), 1):
            lines.append(f"\n--- 章节 {idx}：{l1} ---")

            # 1. 宏观摘要
            if bucket["summaries"]:
                lines.append("\n▎宏观摘要：")
                for s in bucket["summaries"]:
                    lines.append(f"  {s['text']}")

            # 2. 底层原文
            if bucket["leaves"]:
                lines.append("\n▎底层原文：")
                for leaf in bucket["leaves"]:
                    l2 = leaf.get("level_2", "")
                    header = f"  [{l2}] " if l2 else "  "
                    lines.append(f"{header}{leaf['text']}")

            # 3. 交叉引用补充
            if bucket["refs"]:
                lines.append("\n▎交叉引用补充条款：")
                for r in bucket["refs"]:
                    src_tag = r.get("source", "").replace("graph_ref:", "")
                    lines.append(f"  [引用自 {src_tag}]")
                    lines.append(f"  {r['text']}")

        lines.append("\n" + "=" * 40)
        return "\n".join(lines)
